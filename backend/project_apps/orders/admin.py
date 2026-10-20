from django.contrib import admin

from project_apps.orders.models import CheckoutIdempotencyRecord, Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        "variant",
        "product_name",
        "sku",
        "variant_attributes",
        "unit_price",
        "quantity",
        "line_total",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "user",
        "status",
        "payment_status",
        "fulfillment_status",
        "total",
        "currency",
        "created_at",
    )
    list_filter = ("status", "payment_status", "fulfillment_status")
    search_fields = ("order_number", "user__email")
    readonly_fields = (
        "id",
        "order_number",
        "user",
        "cart",
        "subtotal",
        "shipping_fee",
        "discount_amount",
        "tax_amount",
        "total",
        "currency",
        "shipping_address",
        "inventory_restored",
        "created_at",
        "updated_at",
    )
    inlines = [OrderItemInline]


@admin.register(CheckoutIdempotencyRecord)
class CheckoutIdempotencyRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "key", "status", "order", "created_at")
    readonly_fields = (
        "id",
        "user",
        "key",
        "request_fingerprint",
        "status",
        "order",
        "created_at",
        "updated_at",
    )
