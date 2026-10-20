from concurrent.futures import ThreadPoolExecutor, as_completed

from django.db import connections

from project_apps.cart.services import add_item
from project_apps.orders.exceptions import InsufficientStock
from project_apps.orders.models import Order
from project_apps.orders.services import cancel_order, checkout_cart
from project_apps.orders.tests.helpers import ADDRESS, OrdersTransactionTestCase
from project_apps.products.models import ProductVariant


class ConcurrentInventoryTests(OrdersTransactionTestCase):
    def test_two_customers_one_unit_no_oversell(self):
        self.variant.stock = 1
        self.variant.save()
        add_item(self.user, self.variant.pk, 1)
        add_item(self.other_user, self.variant.pk, 1)

        errors = []
        orders = []

        def buy(user, key):
            try:
                order = checkout_cart(
                    user=user,
                    shipping_address=ADDRESS,
                    idempotency_key=key,
                )
                orders.append(order.pk)
            except InsufficientStock as exc:
                errors.append(exc)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(buy, self.user, "concurrent-a"),
                pool.submit(buy, self.other_user, "concurrent-b"),
            ]
            for future in as_completed(futures):
                future.result()

        self.variant.refresh_from_db()
        self.assertEqual(len(orders), 1)
        self.assertEqual(len(errors), 1)
        self.assertEqual(self.variant.stock, 0)
        self.assertEqual(Order.objects.count(), 1)

    def test_multiple_variants_locked_consistently(self):
        self.variant.stock = 5
        self.variant.save()
        variant2 = ProductVariant.objects.create(
            product=self.product,
            sku="ORD-TEST-MULTI",
            price=self.variant.price,
            stock=5,
            is_active=True,
        )
        add_item(self.user, self.variant.pk, 2)
        add_item(self.user, variant2.pk, 3)
        order = checkout_cart(
            user=self.user,
            shipping_address=ADDRESS,
            idempotency_key="multi-variant",
        )
        self.variant.refresh_from_db()
        variant2.refresh_from_db()
        self.assertEqual(self.variant.stock, 3)
        self.assertEqual(variant2.stock, 2)
        self.assertEqual(order.items.count(), 2)

    def test_cancel_restores_stock_once(self):
        self.variant.stock = 4
        self.variant.save()
        add_item(self.user, self.variant.pk, 2)
        order = checkout_cart(
            user=self.user,
            shipping_address=ADDRESS,
            idempotency_key="restore-stock",
        )
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 2)
        cancel_order(order_id=order.pk, user=self.user)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 4)

    def test_concurrent_duplicate_checkout_same_key(self):
        self.variant.stock = 5
        self.variant.save()
        add_item(self.user, self.variant.pk, 1)

        results = []
        errors = []

        def buy():
            try:
                order = checkout_cart(
                    user=self.user,
                    shipping_address=ADDRESS,
                    idempotency_key="same-concurrent-key",
                )
                results.append(order.pk)
            except Exception as exc:
                errors.append(exc)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(buy), pool.submit(buy)]
            for future in as_completed(futures):
                future.result()

        unique_orders = set(results)
        self.assertEqual(len(unique_orders), 1)
        self.assertEqual(Order.objects.filter(user=self.user).count(), 1)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 4)
