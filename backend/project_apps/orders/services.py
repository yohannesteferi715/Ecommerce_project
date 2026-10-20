"""
Order service layer
===================
Checkout, cancellation, inventory adjustment, status transitions, and
the Payments integration boundary live here. Views stay thin.

Inventory strategy (B)
----------------------
Deduct ProductVariant.stock inside the checkout transaction after
locking variant rows in primary-key order. Cancellation restores stock
once, guarded by Order.inventory_restored. Reservations are not used,
so stock is never reserved and deducted for the same purchase.

PostgreSQL row-level locks (SELECT FOR UPDATE) are the concurrency
mechanism. Tests that exercise races use TransactionTestCase.

Payments
--------
checkout_cart does not mark an order paid and does not call a provider.
record_verified_payment_result is the only intended entry point for a
future Payments app after it has verified a provider event.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from project_apps.cart.models import Cart, CartItem
from project_apps.orders.exceptions import (
    CartNotEligible,
    CheckoutInProgress,
    EmptyCart,
    IdempotencyConflict,
    InsufficientStock,
    InvalidAddress,
    InvalidQuantity,
    InvalidTransition,
    OrderAlreadyCancelled,
    OrderError,
    OrderNotCancellable,
    OrderNotFound,
    OrderPricingError,
    PaymentResultError,
    ProductUnavailable,
)
from project_apps.orders.models import (
    CheckoutIdempotencyRecord,
    Order,
    OrderItem,
    generate_order_number,
)
from project_apps.orders.pricing import (
    ZERO,
    calculate_line_total,
    calculate_order_totals,
    get_effective_unit_price,
)
from project_apps.products.models import ProductVariant

ORDER_NUMBER_ATTEMPTS = 8

ALLOWED_ORDER_TRANSITIONS: dict[str, set[str]] = {
    Order.Status.PENDING: {Order.Status.CONFIRMED, Order.Status.CANCELLED},
    Order.Status.CONFIRMED: {Order.Status.PROCESSING, Order.Status.CANCELLED},
    Order.Status.PROCESSING: {Order.Status.COMPLETED},
    Order.Status.COMPLETED: set(),
    Order.Status.CANCELLED: set(),
}

ALLOWED_FULFILLMENT_TRANSITIONS: dict[str, set[str]] = {
    Order.FulfillmentStatus.UNFULFILLED: {Order.FulfillmentStatus.PROCESSING},
    Order.FulfillmentStatus.PROCESSING: {Order.FulfillmentStatus.SHIPPED},
    Order.FulfillmentStatus.SHIPPED: {Order.FulfillmentStatus.DELIVERED},
    Order.FulfillmentStatus.DELIVERED: set(),
}

REQUIRED_ADDRESS_FIELDS = ("full_name", "line1", "city", "postal_code", "country")
OPTIONAL_ADDRESS_FIELDS = ("line2", "state", "phone")
ADDRESS_MAX_LENGTH = 255


def canonicalize_shipping_address(address: dict) -> dict[str, str]:
    """Validate and return a stable, stored address snapshot."""
    if not isinstance(address, dict):
        raise InvalidAddress("Shipping address is required.")

    snapshot: dict[str, str] = {}
    for field in REQUIRED_ADDRESS_FIELDS:
        value = address.get(field)
        if not isinstance(value, str) or not value.strip():
            raise InvalidAddress(f"Shipping address field '{field}' is required.")
        cleaned = value.strip()
        if len(cleaned) > ADDRESS_MAX_LENGTH:
            raise InvalidAddress(f"Shipping address field '{field}' is too long.")
        snapshot[field] = cleaned

    for field in OPTIONAL_ADDRESS_FIELDS:
        value = address.get(field)
        if value is None or value == "":
            snapshot[field] = ""
            continue
        if not isinstance(value, str):
            raise InvalidAddress(f"Shipping address field '{field}' must be a string.")
        cleaned = value.strip()
        if len(cleaned) > ADDRESS_MAX_LENGTH:
            raise InvalidAddress(f"Shipping address field '{field}' is too long.")
        snapshot[field] = cleaned

    country = snapshot["country"]
    if len(country) < 2:
        raise InvalidAddress("Country must be at least 2 characters.")

    return snapshot


def checkout_fingerprint(*, cart_id, shipping_address: dict) -> str:
    payload = {
        "cart_id": cart_id,
        "shipping_address": canonicalize_shipping_address(shipping_address),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _load_order_for_response(order_id) -> Order:
    return (
        Order.objects.select_related("user", "cart")
        .prefetch_related("items")
        .get(pk=order_id)
    )


def _claim_idempotency(*, user, key: str, fingerprint: str) -> CheckoutIdempotencyRecord | Order:
    """
    Insert a claim row, or lock the existing one.

    Returns an Order when this key already succeeded. Returns a
    CheckoutIdempotencyRecord when this transaction owns an in-progress claim.
    """
    try:
        # Isolate the expected unique-key race in a savepoint. Without this,
        # catching IntegrityError leaves the outer checkout transaction unusable.
        with transaction.atomic():
            return CheckoutIdempotencyRecord.objects.create(
                user=user,
                key=key,
                request_fingerprint=fingerprint,
                status=CheckoutIdempotencyRecord.Status.IN_PROGRESS,
            )
    except IntegrityError:
        try:
            record = CheckoutIdempotencyRecord.objects.select_for_update().get(
                user=user, key=key
            )
        except CheckoutIdempotencyRecord.DoesNotExist:
            with transaction.atomic():
                return CheckoutIdempotencyRecord.objects.create(
                    user=user,
                    key=key,
                    request_fingerprint=fingerprint,
                    status=CheckoutIdempotencyRecord.Status.IN_PROGRESS,
                )

        if record.request_fingerprint != fingerprint:
            raise IdempotencyConflict(
                "This idempotency key was already used with different checkout data."
            )
        if record.status == CheckoutIdempotencyRecord.Status.SUCCEEDED and record.order_id:
            return _load_order_for_response(record.order_id)
        if record.status == CheckoutIdempotencyRecord.Status.IN_PROGRESS:
            # Another committed in-progress row should not exist because the
            # claim and the order share one transaction. Treat as a conflict.
            raise CheckoutInProgress(
                "A checkout with this idempotency key is already in progress."
            )
        raise OrderError("Unable to claim checkout idempotency key.")


def _lock_cart(*, user, cart_id) -> Cart:
    qs = Cart.objects.select_for_update().filter(user=user)
    if cart_id is not None:
        qs = qs.filter(pk=cart_id)
    else:
        qs = qs.filter(status=Cart.Status.ACTIVE)

    cart = qs.first()
    if cart is None:
        raise CartNotEligible("Cart not found or does not belong to you.")
    if cart.status != Cart.Status.ACTIVE:
        raise CartNotEligible("This cart is not eligible for checkout.")
    return cart


def _lock_cart_items(cart: Cart) -> list[CartItem]:
    items = list(
        CartItem.objects.select_for_update()
        .select_related("variant", "variant__product")
        .filter(cart=cart)
        .order_by("pk")
    )
    if not items:
        raise EmptyCart("Cannot checkout an empty cart.")
    return items


def _variant_attribute_snapshot(variant: ProductVariant) -> list[dict]:
    rows = variant.variant_attributes.select_related("attribute", "value").all()
    return [
        {"attribute": row.attribute.name, "value": row.value.value}
        for row in rows
    ]


def _deduct_stock(locked_variants: dict[int, ProductVariant], items: list[CartItem]) -> None:
    for item in items:
        variant = locked_variants[item.variant_id]
        if item.quantity < 1:
            raise InvalidQuantity(f"Invalid quantity for SKU {variant.sku}.")
        if variant.stock < item.quantity:
            raise InsufficientStock(
                f"Insufficient stock for SKU {variant.sku}."
            )
        updated = ProductVariant.objects.filter(
            pk=variant.pk,
            stock__gte=item.quantity,
        ).update(stock=F("stock") - item.quantity)
        if updated != 1:
            raise InsufficientStock(
                f"Insufficient stock for SKU {variant.sku}."
            )
        variant.stock -= item.quantity


def _create_order_with_number(**fields) -> Order:
    last_error = None
    for _ in range(ORDER_NUMBER_ATTEMPTS):
        try:
            # A savepoint lets us retry only the rare order-number collision
            # without poisoning checkout's enclosing transaction.
            with transaction.atomic():
                return Order.objects.create(
                    order_number=generate_order_number(),
                    **fields,
                )
        except IntegrityError as exc:
            last_error = exc
    raise OrderError("Could not allocate a unique order number.") from last_error


def checkout_cart(
    *,
    user,
    shipping_address: dict,
    idempotency_key: str,
    cart_id=None,
) -> Order:
    """
    Convert the customer's active (or specified) cart into an Order.

    All database writes happen in one transaction. No payment provider,
    email, or other network I/O is performed.
    """
    if not idempotency_key or not isinstance(idempotency_key, str):
        raise OrderError("An idempotency key is required.")
    key = idempotency_key.strip()
    if not (8 <= len(key) <= 128):
        raise OrderError("Idempotency key must be between 8 and 128 characters.")

    address = canonicalize_shipping_address(shipping_address)
    fingerprint = checkout_fingerprint(cart_id=cart_id, shipping_address=address)

    with transaction.atomic():
        claimed = _claim_idempotency(user=user, key=key, fingerprint=fingerprint)
        if isinstance(claimed, Order):
            return claimed

        cart = _lock_cart(user=user, cart_id=cart_id)
        items = _lock_cart_items(cart)

        variant_ids = sorted({item.variant_id for item in items})
        locked_variants = {
            v.pk: v
            for v in ProductVariant.objects.select_for_update()
            .select_related("product")
            .filter(pk__in=variant_ids)
            .order_by("pk")
        }

        priced_lines: list[dict] = []
        line_totals: list[Decimal] = []
        for item in items:
            variant = locked_variants.get(item.variant_id)
            if variant is None:
                raise ProductUnavailable("A product in the cart is no longer available.")
            if not variant.is_active or not variant.product.is_active:
                raise ProductUnavailable(
                    f"Product '{variant.product.name}' is not available."
                )
            if item.quantity < 1:
                raise InvalidQuantity("Cart item quantity must be at least 1.")

            unit_price = get_effective_unit_price(variant)
            line_total = calculate_line_total(unit_price, item.quantity)
            line_totals.append(line_total)
            priced_lines.append(
                {
                    "variant": variant,
                    "quantity": item.quantity,
                    "unit_price": unit_price,
                    "line_total": line_total,
                    "product_name": variant.product.name,
                    "sku": variant.sku,
                    "variant_attributes": _variant_attribute_snapshot(variant),
                }
            )

        try:
            totals = calculate_order_totals(
                line_totals,
                shipping_fee=ZERO,
                tax_amount=ZERO,
                discount_amount=ZERO,
            )
        except ValueError as exc:
            raise OrderPricingError(str(exc)) from exc

        _deduct_stock(locked_variants, items)

        currency = getattr(settings, "DEFAULT_CURRENCY", "USD")
        order = _create_order_with_number(
            user=user,
            cart=cart,
            status=Order.Status.PENDING,
            payment_status=Order.PaymentStatus.UNPAID,
            fulfillment_status=Order.FulfillmentStatus.UNFULFILLED,
            subtotal=totals.subtotal,
            shipping_fee=totals.shipping_fee,
            discount_amount=totals.discount_amount,
            tax_amount=totals.tax_amount,
            total=totals.total,
            currency=currency,
            shipping_address=address,
        )

        OrderItem.objects.bulk_create(
            [
                OrderItem(
                    order=order,
                    variant=line["variant"],
                    product_name=line["product_name"],
                    sku=line["sku"],
                    variant_attributes=line["variant_attributes"],
                    unit_price=line["unit_price"],
                    quantity=line["quantity"],
                    line_total=line["line_total"],
                )
                for line in priced_lines
            ]
        )

        cart.status = Cart.Status.CHECKED_OUT
        cart.save(update_fields=["status", "updated_at"])

        claimed.status = CheckoutIdempotencyRecord.Status.SUCCEEDED
        claimed.order = order
        claimed.save(update_fields=["status", "order", "updated_at"])

        return _load_order_for_response(order.pk)


def _restore_inventory(order: Order) -> None:
    if order.inventory_restored:
        return

    items = list(order.items.exclude(variant_id=None).order_by("variant_id"))
    variant_ids = sorted({item.variant_id for item in items})
    if variant_ids:
        list(
            ProductVariant.objects.select_for_update()
            .filter(pk__in=variant_ids)
            .order_by("pk")
        )
        for item in items:
            ProductVariant.objects.filter(pk=item.variant_id).update(
                stock=F("stock") + item.quantity
            )

    order.inventory_restored = True


def _apply_status(order: Order, new_status: str) -> None:
    allowed = ALLOWED_ORDER_TRANSITIONS.get(order.status, set())
    if new_status not in allowed:
        raise InvalidTransition(
            f"Cannot transition order from '{order.status}' to '{new_status}'."
        )
    order.status = new_status


def transition_order_status(*, order_id, user, new_status: str) -> Order:
    """Allow staff to apply explicit order-status transitions."""
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(pk=order_id)
        except Order.DoesNotExist:
            raise OrderNotFound("Order not found.")
        if not user.is_staff:
            raise OrderNotFound("Order not found.")
        _apply_status(order, new_status)
        order.save(update_fields=["status", "updated_at"])
        return order


def transition_fulfillment_status(*, order_id, user, new_status: str) -> Order:
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(pk=order_id)
        except Order.DoesNotExist:
            raise OrderNotFound("Order not found.")
        if not user.is_staff:
            raise OrderNotFound("Order not found.")
        allowed = ALLOWED_FULFILLMENT_TRANSITIONS.get(order.fulfillment_status, set())
        if new_status not in allowed:
            raise InvalidTransition(
                f"Cannot transition fulfillment from "
                f"'{order.fulfillment_status}' to '{new_status}'."
            )
        order.fulfillment_status = new_status
        if (
            new_status == Order.FulfillmentStatus.PROCESSING
            and order.status == Order.Status.CONFIRMED
        ):
            _apply_status(order, Order.Status.PROCESSING)
        if (
            new_status == Order.FulfillmentStatus.DELIVERED
            and order.status == Order.Status.PROCESSING
        ):
            _apply_status(order, Order.Status.COMPLETED)
        order.save(update_fields=["status", "fulfillment_status", "updated_at"])
        return order


def cancel_order(*, order_id, user, reason: str = "") -> Order:
    """
    Cancel an eligible order and restore deducted stock once.

    Does not contact a payment provider. If payment_status is paid,
    it stays paid; a future Payments app should request a refund after
    commit via its own workflow.
    """
    reason = (reason or "").strip()[:500]

    with transaction.atomic():
        try:
            order = (
                Order.objects.select_for_update()
                .prefetch_related("items")
                .get(pk=order_id)
            )
        except Order.DoesNotExist:
            raise OrderNotFound("Order not found.")

        if order.user_id != user.pk and not getattr(user, "is_staff", False):
            raise OrderNotFound("Order not found.")

        if order.status == Order.Status.CANCELLED:
            raise OrderAlreadyCancelled("This order is already cancelled.")

        if not order.is_cancellable:
            raise OrderNotCancellable(
                "This order can no longer be cancelled."
            )

        _apply_status(order, Order.Status.CANCELLED)
        _restore_inventory(order)
        order.cancellation_reason = reason
        order.cancelled_at = timezone.now()
        order.save(
            update_fields=[
                "status",
                "inventory_restored",
                "cancellation_reason",
                "cancelled_at",
                "updated_at",
            ]
        )
        return _load_order_for_response(order.pk)


def record_verified_payment_result(
    *,
    order_id,
    result: str,
) -> Order:
    """
    Payments integration point.

    Call this only after a future Payments app has verified a provider
    event (webhook signature, captured charge, etc.). Customers must
    never hit this function through a public serializer.

    result:
      paid     — payment_status=paid; pending orders become confirmed
      failed   — payment_status=failed; order remains unless already cancelled
      refunded — payment_status=refunded; fulfillment/order status unchanged
      pending  — payment_status=pending (authorization started)

    A failed payment does not delete the order. A refund does not imply
    the goods were never delivered.
    """
    allowed = {
        Order.PaymentStatus.PAID,
        Order.PaymentStatus.FAILED,
        Order.PaymentStatus.REFUNDED,
        Order.PaymentStatus.PENDING,
    }
    if result not in allowed:
        raise PaymentResultError(f"Unknown payment result '{result}'.")

    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(pk=order_id)
        except Order.DoesNotExist:
            raise OrderNotFound("Order not found.")

        if (
            result == Order.PaymentStatus.PAID
            and order.payment_status == Order.PaymentStatus.PAID
        ):
            return order

        order.payment_status = result
        update_fields = ["payment_status", "updated_at"]

        if result == Order.PaymentStatus.PAID and order.status == Order.Status.PENDING:
            _apply_status(order, Order.Status.CONFIRMED)
            update_fields.append("status")

        order.save(update_fields=update_fields)
        return order
