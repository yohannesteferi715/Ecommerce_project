"""
Order models
============
Order            — a completed checkout, with historical money and address
OrderItem        — one purchased variant line with price/SKU snapshots
CheckoutIdempotencyRecord — durable per-user idempotency claim for checkout

Prices on Order/OrderItem are snapshots. Later catalog edits do not
rewrite past purchases. Inventory lives on products.ProductVariant.stock;
this app deducts and restores that counter rather than introducing a
second stock field.
"""

from __future__ import annotations

import secrets
import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


def default_currency() -> str:
    return getattr(settings, "DEFAULT_CURRENCY", "USD")


def generate_order_number() -> str:
    """
    Public order number. Uniqueness is enforced by a UniqueConstraint;
    callers must retry on IntegrityError rather than checking existence
    then inserting.
    """
    date_part = timezone.now().strftime("%Y%m%d")
    suffix = secrets.token_hex(4).upper()
    return f"ORD-{date_part}-{suffix}"


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    class FulfillmentStatus(models.TextChoices):
        UNFULFILLED = "unfulfilled", "Unfulfilled"
        PROCESSING = "processing", "Processing"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(max_length=32, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    cart = models.ForeignKey(
        "cart.Cart",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID,
        db_index=True,
    )
    fulfillment_status = models.CharField(
        max_length=20,
        choices=FulfillmentStatus.choices,
        default=FulfillmentStatus.UNFULFILLED,
        db_index=True,
    )
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    shipping_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    currency = models.CharField(max_length=3, default=default_currency)
    shipping_address = models.JSONField()
    cancellation_reason = models.CharField(max_length=500, blank=True, default="")
    cancelled_at = models.DateTimeField(null=True, blank=True)
    inventory_restored = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(subtotal__gte=0),
                name="order_subtotal_gte_0",
            ),
            models.CheckConstraint(
                check=models.Q(shipping_fee__gte=0),
                name="order_shipping_fee_gte_0",
            ),
            models.CheckConstraint(
                check=models.Q(discount_amount__gte=0),
                name="order_discount_amount_gte_0",
            ),
            models.CheckConstraint(
                check=models.Q(tax_amount__gte=0),
                name="order_tax_amount_gte_0",
            ),
            models.CheckConstraint(
                check=models.Q(total__gte=0),
                name="order_total_gte_0",
            ),
            models.CheckConstraint(
                check=models.Q(
                    total=models.F("subtotal")
                    + models.F("shipping_fee")
                    + models.F("tax_amount")
                    - models.F("discount_amount")
                ),
                name="order_total_matches_components",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.order_number} [{self.status}]"

    @property
    def is_cancellable(self) -> bool:
        return (
            self.status in (self.Status.PENDING, self.Status.CONFIRMED)
            and self.fulfillment_status == self.FulfillmentStatus.UNFULFILLED
        )


class OrderItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )
    variant = models.ForeignKey(
        "products.ProductVariant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )
    product_name = models.CharField(max_length=255)
    sku = models.CharField(max_length=100)
    variant_attributes = models.JSONField(default=list, blank=True)
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    line_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        ordering = ["product_name", "sku"]
        constraints = [
            models.UniqueConstraint(
                fields=["order", "variant"],
                name="unique_variant_per_order",
            ),
            models.CheckConstraint(
                check=models.Q(quantity__gte=1),
                name="orderitem_quantity_gte_1",
            ),
            models.CheckConstraint(
                check=models.Q(unit_price__gte=0),
                name="orderitem_unit_price_gte_0",
            ),
            models.CheckConstraint(
                check=models.Q(line_total__gte=0),
                name="orderitem_line_total_gte_0",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.sku} × {self.quantity} ({self.order.order_number})"


class CheckoutIdempotencyRecord(models.Model):
    """
    Durable checkout claim scoped to a user.

    Inserted inside the same database transaction as the order. A process
    crash before commit rolls the claim back, so a retry with the same key
    may proceed. After commit, the same key returns the original order.
    """

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        SUCCEEDED = "succeeded", "Succeeded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="checkout_idempotency_keys",
    )
    key = models.CharField(max_length=128)
    request_fingerprint = models.CharField(max_length=64)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="idempotency_records",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "key"],
                name="unique_checkout_idempotency_key_per_user",
            )
        ]

    def __str__(self) -> str:
        return f"CheckoutIdempotency({self.user_id}, {self.key})"
