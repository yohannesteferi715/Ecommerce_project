from decimal import Decimal
from unittest.mock import patch

from rest_framework import status

from project_apps.cart.models import Cart, CartItem
from project_apps.cart.services import add_item, get_or_create_cart
from project_apps.orders.exceptions import (
    CartNotEligible,
    EmptyCart,
    InsufficientStock,
    InvalidQuantity,
    ProductUnavailable,
)
from project_apps.orders.models import Order, OrderItem
from project_apps.orders.services import checkout_cart
from project_apps.orders.tests.helpers import (
    ADDRESS,
    CHECKOUT_URL,
    OrdersTestCase,
)
from project_apps.products.models import ProductVariant


class CheckoutServiceTests(OrdersTestCase):
    def test_successful_checkout(self):
        add_item(self.user, self.variant.pk, 2)
        add_item(self.user, self.variant2.pk, 1)
        order = checkout_cart(
            user=self.user,
            shipping_address=ADDRESS,
            idempotency_key="checkout-success-1",
        )
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.payment_status, Order.PaymentStatus.UNPAID)
        expected = self.variant.price * 2 + self.variant2.price
        self.assertEqual(order.subtotal, expected)
        self.assertEqual(order.total, expected)
        self.assertEqual(order.items.count(), 2)
        cart = Cart.objects.get(pk=order.cart_id)
        self.assertEqual(cart.status, Cart.Status.CHECKED_OUT)

    def test_empty_cart_rejected(self):
        get_or_create_cart(self.user)
        with self.assertRaises(EmptyCart):
            checkout_cart(
                user=self.user,
                shipping_address=ADDRESS,
                idempotency_key="empty-cart-key",
            )

    def test_missing_cart_rejected(self):
        with self.assertRaises(CartNotEligible):
            checkout_cart(
                user=self.user,
                shipping_address=ADDRESS,
                idempotency_key="no-cart-key",
            )

    def test_other_users_cart_rejected(self):
        item = add_item(self.user, self.variant.pk, 1)
        with self.assertRaises(CartNotEligible):
            checkout_cart(
                user=self.other_user,
                shipping_address=ADDRESS,
                idempotency_key="steal-cart-key",
                cart_id=item.cart_id,
            )

    def test_inactive_cart_rejected(self):
        item = add_item(self.user, self.variant.pk, 1)
        cart = item.cart
        cart.status = Cart.Status.ABANDONED
        cart.save()
        with self.assertRaises(CartNotEligible):
            checkout_cart(
                user=self.user,
                shipping_address=ADDRESS,
                idempotency_key="abandoned-cart",
                cart_id=cart.pk,
            )

    def test_insufficient_stock(self):
        self.variant.stock = 1
        self.variant.save()
        add_item(self.user, self.variant.pk, 2)
        with self.assertRaises(InsufficientStock):
            checkout_cart(
                user=self.user,
                shipping_address=ADDRESS,
                idempotency_key="low-stock",
            )
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 1)
        self.assertEqual(Order.objects.count(), 0)
        cart = Cart.objects.get(user=self.user)
        self.assertEqual(cart.status, Cart.Status.ACTIVE)

    def test_inactive_variant_rejected(self):
        add_item(self.user, self.variant.pk, 1)
        self.variant.is_active = False
        self.variant.save()
        with self.assertRaises(ProductUnavailable):
            checkout_cart(
                user=self.user,
                shipping_address=ADDRESS,
                idempotency_key="inactive-variant",
            )

    def test_historical_price_and_address(self):
        add_item(self.user, self.variant.pk, 2)
        order = checkout_cart(
            user=self.user,
            shipping_address=ADDRESS,
            idempotency_key="snapshot-key",
        )
        item = order.items.get()
        self.variant.price = Decimal("5.00")
        self.variant.save()
        self.product.name = "Renamed"
        self.product.save()
        item.refresh_from_db()
        self.assertEqual(item.unit_price, Decimal("29.99"))
        self.assertEqual(item.line_total, Decimal("59.98"))
        self.assertEqual(item.product_name, "Order Test Product")
        self.assertEqual(order.shipping_address["line1"], "1 High Street")

    def test_price_change_uses_checkout_price(self):
        add_item(self.user, self.variant.pk, 1)
        self.variant.price = Decimal("40.00")
        self.variant.save()
        order = checkout_cart(
            user=self.user,
            shipping_address=ADDRESS,
            idempotency_key="price-change",
        )
        item = order.items.get()
        self.assertEqual(item.unit_price, Decimal("40.00"))
        self.assertEqual(order.total, Decimal("40.00"))

    def test_stock_deducted(self):
        add_item(self.user, self.variant.pk, 3)
        checkout_cart(
            user=self.user,
            shipping_address=ADDRESS,
            idempotency_key="deduct-stock",
        )
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 97)

    def test_rollback_on_item_insert_failure(self):
        add_item(self.user, self.variant.pk, 1)
        with patch(
            "project_apps.orders.services.OrderItem.objects.bulk_create",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                checkout_cart(
                    user=self.user,
                    shipping_address=ADDRESS,
                    idempotency_key="rollback-key",
                )
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 100)
        self.assertEqual(Order.objects.count(), 0)
        cart = Cart.objects.get(user=self.user)
        self.assertEqual(cart.status, Cart.Status.ACTIVE)

    def test_missing_variant_during_lock(self):
        add_item(self.user, self.variant.pk, 1)

        class EmptyLock:
            def select_related(self, *args, **kwargs):
                return self

            def filter(self, *args, **kwargs):
                return self

            def order_by(self, *args, **kwargs):
                return ProductVariant.objects.none()

        with patch(
            "project_apps.orders.services.ProductVariant.objects.select_for_update",
            return_value=EmptyLock(),
        ):
            with self.assertRaises(ProductUnavailable):
                checkout_cart(
                    user=self.user,
                    shipping_address=ADDRESS,
                    idempotency_key="deleted-variant",
                )

    def test_invalid_quantity_rejected(self):
        item = add_item(self.user, self.variant.pk, 1)
        CartItem.objects.filter(pk=item.pk).update(quantity=0)
        with self.assertRaises(InvalidQuantity):
            checkout_cart(
                user=self.user,
                shipping_address=ADDRESS,
                idempotency_key="zero-qty",
            )

    def test_checkout_does_not_mark_paid(self):
        add_item(self.user, self.variant.pk, 1)
        order = checkout_cart(
            user=self.user,
            shipping_address=ADDRESS,
            idempotency_key="unpaid-key",
        )
        self.assertEqual(order.payment_status, Order.PaymentStatus.UNPAID)
        self.assertEqual(order.status, Order.Status.PENDING)


class CheckoutAPITests(OrdersTestCase):
    def test_unauthenticated_checkout(self):
        res = self._unauth().post(CHECKOUT_URL, {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_successful_http_checkout(self):
        add_item(self.user, self.variant.pk, 1)
        res = self._auth().post(
            CHECKOUT_URL,
            {
                "idempotency_key": "api-success",
                "shipping_address": ADDRESS,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        body = res.json()
        self.assertEqual(body["payment_status"], "unpaid")
        self.assertEqual(Decimal(body["total"]), Decimal("29.99"))
        self.assertEqual(len(body["items"]), 1)
        self.assertNotIn("inventory_restored", body)

    def test_client_prices_ignored(self):
        add_item(self.user, self.variant.pk, 1)
        res = self._auth().post(
            CHECKOUT_URL,
            {
                "idempotency_key": "ignore-prices",
                "shipping_address": ADDRESS,
                "total": "0.01",
                "subtotal": "0.01",
                "payment_status": "paid",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.json()["payment_status"], "unpaid")
        self.assertEqual(Decimal(res.json()["total"]), Decimal("29.99"))

    def test_missing_address_returns_400(self):
        add_item(self.user, self.variant.pk, 1)
        res = self._auth().post(
            CHECKOUT_URL,
            {"idempotency_key": "no-address"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_idempotency_header(self):
        add_item(self.user, self.variant.pk, 1)
        res = self._auth().post(
            CHECKOUT_URL,
            {"shipping_address": ADDRESS},
            format="json",
            HTTP_IDEMPOTENCY_KEY="header-key-123",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
