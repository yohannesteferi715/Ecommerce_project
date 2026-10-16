"""
Cart serializers
================
Responsibilities
----------------
- Request validation only (variant_id, quantity).
- Response shaping — never accepts prices or totals from the client.
- Delegates all business logic to services.py.

Serializer map
--------------
AddItemSerializer          — validates POST /api/cart/items/
SetQuantitySerializer      — validates PATCH /api/cart/items/{id}/
CartItemSerializer         — shapes a single CartItem in responses
CartSerializer             — shapes the full cart in GET /api/cart/
"""

from __future__ import annotations

from django.conf import settings

from rest_framework import serializers

from project_apps.cart.models import Cart, CartItem
from project_apps.cart.services import get_item_availability, get_cart_totals

MAX_QTY: int = getattr(settings, "MAX_CART_ITEM_QUANTITY", 99)


# ---------------------------------------------------------------------------
# Request serializers
# ---------------------------------------------------------------------------

class AddItemSerializer(serializers.Serializer):
    """Validates the body of POST /api/cart/items/."""

    variant_id = serializers.IntegerField(
        min_value=1,
        help_text="Primary key of the ProductVariant to add.",
    )
    quantity = serializers.IntegerField(
        min_value=1,
        max_value=MAX_QTY,
        help_text=f"Number of units to add (1–{MAX_QTY}).",
    )


class SetQuantitySerializer(serializers.Serializer):
    """Validates the body of PATCH /api/cart/items/{id}/."""

    quantity = serializers.IntegerField(
        min_value=1,
        max_value=MAX_QTY,
        help_text=f"New absolute quantity for this item (1–{MAX_QTY}).",
    )


# ---------------------------------------------------------------------------
# Response serializers
# ---------------------------------------------------------------------------

class VariantSummarySerializer(serializers.Serializer):
    """
    Lightweight read-only variant summary embedded in cart item responses.
    Keeps the cart response self-contained without importing the full
    ProductVariantSerializer (which carries heavy nested data).
    """
    id = serializers.IntegerField(read_only=True)
    sku = serializers.CharField(read_only=True)
    product_id = serializers.IntegerField(read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    price = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    discount_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True, allow_null=True
    )


class CartItemSerializer(serializers.ModelSerializer):
    """
    Serializes a CartItem for inclusion in the cart response.

    Prices are always read from the variant at serialization time — never
    stored on the item and never accepted from the client.
    """
    variant = VariantSummarySerializer(read_only=True)

    # Computed from variant at serialization time
    unit_price = serializers.SerializerMethodField(
        help_text="Effective unit price (respects active discount window)."
    )
    line_total = serializers.SerializerMethodField(
        help_text="unit_price × quantity."
    )

    # Current availability status for this item
    availability = serializers.SerializerMethodField(
        help_text="Real-time availability of this variant."
    )

    class Meta:
        model = CartItem
        fields = [
            "id",
            "variant",
            "quantity",
            "unit_price",
            "line_total",
            "availability",
            "added_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_unit_price(self, obj: CartItem):
        return str(obj.unit_price)

    def get_line_total(self, obj: CartItem):
        return str(obj.line_total)

    def get_availability(self, obj: CartItem):
        return get_item_availability(obj)


class CartSerializer(serializers.ModelSerializer):
    """
    Full cart response serializer.

    Totals are computed from current backend prices; the client never
    supplies or influences them.
    """
    items = CartItemSerializer(many=True, read_only=True)
    subtotal = serializers.SerializerMethodField(
        help_text="Sum of all line totals at current prices (provisional)."
    )
    item_count = serializers.SerializerMethodField(
        help_text="Number of distinct line items in the cart."
    )
    total_units = serializers.SerializerMethodField(
        help_text="Sum of all item quantities."
    )

    class Meta:
        model = Cart
        fields = [
            "id",
            "status",
            "items",
            "subtotal",
            "item_count",
            "total_units",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_subtotal(self, obj: Cart) -> str:
        return str(get_cart_totals(obj)["subtotal"])

    def get_item_count(self, obj: Cart) -> int:
        return get_cart_totals(obj)["item_count"]

    def get_total_units(self, obj: Cart) -> int:
        return get_cart_totals(obj)["total_units"]
