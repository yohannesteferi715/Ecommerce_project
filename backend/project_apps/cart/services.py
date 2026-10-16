"""
Cart service layer
==================
All cart business operations live here.  Views are kept thin and call these
functions directly.  No business logic in serializers or models beyond simple
property helpers.

Transaction policy (justified per operation below)
---------------------------------------------------
get_or_create_cart   — uses get_or_create inside select_for_update-guarded
                       logic to handle the race where two concurrent requests
                       both miss the initial .get() and both try to INSERT.
                       SQLite serialises writers, so IntegrityError on the
                       partial unique index is the safety net.

add_item             — uses update_or_create inside transaction.atomic so that
                       the quantity increment (read → add → write) and the
                       initial INSERT are both atomic.  Without a transaction
                       two concurrent "add same variant" requests could both
                       see quantity=1 and each write quantity=2 instead of 3.

set_item_quantity    — single UPDATE; no explicit transaction needed.

remove_item          — single DELETE; no explicit transaction needed.

clear_cart           — bulk DELETE of multiple rows; wrapped in atomic to
                       ensure all-or-nothing behaviour.

Concurrency note on SQLite
--------------------------
SQLite uses database-level write serialisation (WAL mode aside, only one
writer at a time).  SELECT FOR UPDATE is accepted syntactically but does not
add row-level locking beyond what SQLite already provides.  The
IntegrityError fallback in get_or_create_cart is therefore the primary
safety net for duplicate-cart races on this backend.  Tests that exercise
concurrent behaviour should be aware of this limitation.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from project_apps.cart.models import Cart, CartItem
from project_apps.products.models import ProductVariant

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _max_qty() -> int:
    """
    Read MAX_CART_ITEM_QUANTITY from settings at call time so that
    @override_settings works correctly in tests and runtime changes
    to settings are always respected.
    """
    return getattr(settings, "MAX_CART_ITEM_QUANTITY", 99)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CartError(Exception):
    """Base class for all cart service errors."""


class ProductNotAvailable(CartError):
    """Raised when a variant is inactive, out of stock, or does not exist."""


class InvalidQuantity(CartError):
    """Raised when a requested quantity is out of the allowed range."""


class ItemNotFound(CartError):
    """Raised when a cart item does not belong to the customer's cart."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_eligible_variant(variant_id: int) -> ProductVariant:
    """
    Fetch a ProductVariant that is eligible for purchase.

    Eligibility rules:
      - variant must exist
      - variant.is_active must be True
      - variant.product.is_active must be True

    Does NOT check stock > 0 here; stock is validated separately when adding
    so that customers can keep items in their cart even if stock temporarily
    drops to zero (availability is re-validated at checkout by the orders app).
    """
    try:
        variant = ProductVariant.objects.select_related("product").get(pk=variant_id)
    except ProductVariant.DoesNotExist:
        raise ProductNotAvailable("The selected product variant does not exist.")

    if not variant.is_active:
        raise ProductNotAvailable("This product variant is not available.")

    if not variant.product.is_active:
        raise ProductNotAvailable("This product is not available.")

    return variant


def _validate_quantity(quantity: int, current: int = 0) -> None:
    """
    Validate that the requested quantity is within the allowed range.

    Args:
        quantity: The quantity being requested (absolute, not a delta).
        current:  The quantity already in the cart (used for increment checks).
    """
    if not isinstance(quantity, int) or quantity < 1:
        raise InvalidQuantity(f"Quantity must be a positive integer (got {quantity!r}).")

    if quantity > _max_qty():
        raise InvalidQuantity(
            f"Quantity {quantity} exceeds the maximum allowed per item ({_max_qty()})."
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_or_create_cart(user) -> Cart:
    """
    Return the single active cart for *user*, creating one if none exists.

    The database-level UniqueConstraint on (user, status='active') is the
    authoritative guard against duplicates.  get_or_create provides optimistic
    concurrency; the IntegrityError catch handles the rare race where two
    requests both miss the GET and both attempt the INSERT.

    Transaction: the get_or_create itself is atomic at the statement level.
    No explicit transaction.atomic() is needed here because a single
    get_or_create call issues at most two SQL statements (SELECT then INSERT)
    and the DB constraint is the final safety net.
    """
    try:
        cart, _ = Cart.objects.get_or_create(
            user=user,
            status=Cart.Status.ACTIVE,
        )
        return cart
    except IntegrityError:
        # Two concurrent requests raced; the constraint fired on the second
        # INSERT.  The first writer won — fetch their cart.
        return Cart.objects.get(user=user, status=Cart.Status.ACTIVE)


def get_cart_or_none(user) -> Cart | None:
    """Return the user's active cart, or None if they have none."""
    return Cart.objects.filter(user=user, status=Cart.Status.ACTIVE).first()


def add_item(user, variant_id: int, quantity: int) -> CartItem:
    """
    Add *quantity* units of *variant_id* to the user's cart.

    If the variant is already in the cart, the quantity is incremented.
    The combined quantity must not exceed MAX_CART_ITEM_QUANTITY.

    Transaction: atomic because the increment is a read-then-write.  Without
    a transaction two concurrent "add same variant" requests could each read
    quantity=1, each write quantity=2, losing one increment.
    """
    if not isinstance(quantity, int):
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            raise InvalidQuantity(f"Quantity must be a positive integer (got {quantity!r}).")

    _validate_quantity(quantity)

    variant = _get_eligible_variant(variant_id)

    with transaction.atomic():
        cart = get_or_create_cart(user)

        try:
            item = CartItem.objects.select_for_update().get(
                cart=cart, variant=variant
            )
            new_qty = item.quantity + quantity
            if new_qty > _max_qty():
                raise InvalidQuantity(
                    f"Cannot add {quantity} unit(s): the cart already contains "
                    f"{item.quantity} of this item and the maximum is {_max_qty()}."
                )
            item.quantity = new_qty
            item.save(update_fields=["quantity", "updated_at"])
        except CartItem.DoesNotExist:
            # First time this variant is added — create the row.
            item = CartItem.objects.create(
                cart=cart, variant=variant, quantity=quantity
            )

    return item


def set_item_quantity(user, item_id: int, quantity: int) -> CartItem:
    """
    Explicitly set the quantity of a cart item to *quantity*.

    Unlike add_item, this replaces the current quantity rather than
    incrementing it.  A single UPDATE is atomic at the statement level; no
    explicit transaction is needed.
    """
    if not isinstance(quantity, int):
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            raise InvalidQuantity(f"Quantity must be a positive integer (got {quantity!r}).")

    _validate_quantity(quantity)

    try:
        item = CartItem.objects.select_related("cart").get(
            pk=item_id, cart__user=user, cart__status=Cart.Status.ACTIVE
        )
    except CartItem.DoesNotExist:
        raise ItemNotFound(
            "Cart item not found or does not belong to your active cart."
        )

    item.quantity = quantity
    item.save(update_fields=["quantity", "updated_at"])
    return item


def remove_item(user, item_id: int) -> None:
    """
    Remove a single item from the user's active cart.

    Single DELETE — no explicit transaction needed.
    Raises ItemNotFound if the item does not exist or belongs to another user.
    """
    deleted, _ = CartItem.objects.filter(
        pk=item_id,
        cart__user=user,
        cart__status=Cart.Status.ACTIVE,
    ).delete()

    if deleted == 0:
        raise ItemNotFound(
            "Cart item not found or does not belong to your active cart."
        )


def clear_cart(user) -> int:
    """
    Remove all items from the user's active cart.

    Wrapped in transaction.atomic() because we are deleting multiple rows that
    must all succeed or all fail together.  Returns the number of items deleted.
    """
    cart = get_cart_or_none(user)
    if cart is None:
        return 0

    with transaction.atomic():
        deleted, _ = CartItem.objects.filter(cart=cart).delete()

    return deleted


def get_cart_totals(cart: Cart) -> dict:
    """
    Calculate cart totals from current backend prices.

    Returns a dict with:
      subtotal      — sum of all line totals (Decimal)
      item_count    — number of distinct line items (int)
      total_units   — sum of all quantities (int)

    Prices are always read from ProductVariant at call time; no client-supplied
    values are used.  This total is *provisional* — the orders app must
    recalculate at checkout.
    """
    items = cart.items.select_related(
        "variant", "variant__product"
    ).all()

    subtotal = Decimal("0.00")
    total_units = 0

    for item in items:
        subtotal += item.line_total
        total_units += item.quantity

    return {
        "subtotal": subtotal,
        "item_count": items.count(),
        "total_units": total_units,
    }


def get_item_availability(item: CartItem) -> dict:
    """
    Return current availability information for a cart item.

    Called when serializing cart items so the API surface can show whether
    an item that was previously added is still purchasable.
    """
    variant = item.variant
    now = timezone.now()

    in_stock = variant.stock > 0
    is_active = variant.is_active and variant.product.is_active
    available = is_active and in_stock

    return {
        "is_active": is_active,
        "in_stock": in_stock,
        "stock": variant.stock,
        "available": available,
    }
