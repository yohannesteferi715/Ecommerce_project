"""
Order serializers — request validation and response shaping only.
Business logic lives in services.py.
"""

from __future__ import annotations

from rest_framework import serializers

from project_apps.orders.models import Order, OrderItem


class ShippingAddressSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)
    line1 = serializers.CharField(max_length=255)
    line2 = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    city = serializers.CharField(max_length=255)
    state = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    postal_code = serializers.CharField(max_length=255)
    country = serializers.CharField(min_length=2, max_length=255)
    phone = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class CheckoutRequestSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(min_length=8, max_length=128)
    cart_id = serializers.IntegerField(min_value=1, required=False)
    shipping_address = ShippingAddressSerializer()

    def to_internal_value(self, data):
        # Drop client-supplied financial fields rather than trusting them.
        if hasattr(data, "copy"):
            data = data.copy()
            for key in (
                "subtotal",
                "total",
                "unit_price",
                "line_total",
                "discount_amount",
                "tax_amount",
                "shipping_fee",
                "status",
                "payment_status",
                "user_id",
            ):
                data.pop(key, None)
        return super().to_internal_value(data)


class CancelOrderSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = [
            "id",
            "variant",
            "product_name",
            "sku",
            "variant_attributes",
            "unit_price",
            "quantity",
            "line_total",
        ]
        read_only_fields = fields


class OrderListSerializer(serializers.ModelSerializer):
    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "status",
            "payment_status",
            "fulfillment_status",
            "subtotal",
            "shipping_fee",
            "discount_amount",
            "tax_amount",
            "total",
            "currency",
            "item_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "status",
            "payment_status",
            "fulfillment_status",
            "subtotal",
            "shipping_fee",
            "discount_amount",
            "tax_amount",
            "total",
            "currency",
            "shipping_address",
            "cancellation_reason",
            "cancelled_at",
            "items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
