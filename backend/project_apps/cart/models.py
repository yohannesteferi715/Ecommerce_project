"""
Cart models
===========
Two tables:

  Cart       — one active cart per customer (enforced by UniqueConstraint)
  CartItem   — one row per (cart, variant) pair (enforced by unique_together)

Design notes
------------
- The cart references ProductVariant directly.  The Product can be reached via
  variant.product.  This is correct because price, stock, and availability all
  live on the variant, not the product.
- Cart.status uses string choices so the orders app can transition a cart to
  'checked_out' without needing extra columns.
- CartItem stores no price snapshot.  Prices are always read from
  ProductVariant at query time.  The orders app must snapshot prices at
  checkout time — that is not the cart's responsibility.
- A database-level UniqueConstraint on (user, status='active') prevents
  duplicate active carts.
- created_at / updated_at follow the convention of every other model in this
  project.
"""

from django.conf import settings
from django.db import models


class Cart(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CHECKED_OUT = "checked_out", "Checked Out"
        ABANDONED = "abandoned", "Abandoned"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="carts",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # One active cart per customer at the database level.
        # The condition mirrors Cart.Status.ACTIVE so the constraint is a
        # partial unique index — other statuses are unconstrained, which allows
        # order history to keep completed carts.
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(status="active"),
                name="unique_active_cart_per_user",
            )
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Cart({self.pk}) — {self.user} [{self.status}]"

    # ------------------------------------------------------------------
    # Convenience helpers (no business logic — kept deliberately thin)
    # ------------------------------------------------------------------

    @property
    def item_count(self):
        return self.items.count()

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items",
    )
    variant = models.ForeignKey(
        # Use app_label string reference to avoid a hard import cycle.
        "products.ProductVariant",
        on_delete=models.CASCADE,
        related_name="cart_items",
    )
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # One row per (cart, variant) — duplicates must accumulate via
        # quantity increments, not extra rows.
        unique_together = ("cart", "variant")
        ordering = ["added_at"]

    def __str__(self):
        return (
            f"CartItem({self.pk}) — "
            f"{self.variant.sku} × {self.quantity} in Cart({self.cart_id})"
        )

    # ------------------------------------------------------------------
    # Read-only price helpers — prices always sourced from the variant,
    # never stored on the cart item.
    # ------------------------------------------------------------------

    @property
    def unit_price(self):
        """Effective price at query time (respects active discount window)."""
        from django.utils import timezone

        v = self.variant
        now = timezone.now()
        if (
            v.discount_price is not None
            and v.discount_start is not None
            and v.discount_end is not None
            and v.discount_start <= now <= v.discount_end
        ):
            return v.discount_price
        return v.price

    @property
    def line_total(self):
        return self.unit_price * self.quantity
