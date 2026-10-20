from rest_framework import status

from project_apps.cart.models import Cart
from project_apps.cart.services import add_item
from project_apps.orders.exceptions import IdempotencyConflict
from project_apps.orders.models import CheckoutIdempotencyRecord, Order
from project_apps.orders.services import checkout_cart
from project_apps.orders.tests.helpers import ADDRESS, CHECKOUT_URL, OrdersTestCase


class IdempotencyTests(OrdersTestCase):
    def test_repeated_key_returns_same_order(self):
        add_item(self.user, self.variant.pk, 1)
        first = checkout_cart(
            user=self.user,
            shipping_address=ADDRESS,
            idempotency_key="same-key-once",
        )
        second = checkout_cart(
            user=self.user,
            shipping_address=ADDRESS,
            idempotency_key="same-key-once",
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Order.objects.filter(user=self.user).count(), 1)

    def test_same_key_different_params_rejected(self):
        add_item(self.user, self.variant.pk, 1)
        checkout_cart(
            user=self.user,
            shipping_address=ADDRESS,
            idempotency_key="conflict-key",
        )
        other_address = {**ADDRESS, "city": "Manchester"}
        with self.assertRaises(IdempotencyConflict):
            checkout_cart(
                user=self.user,
                shipping_address=other_address,
                idempotency_key="conflict-key",
            )

    def test_database_uniqueness(self):
        add_item(self.user, self.variant.pk, 1)
        checkout_cart(
            user=self.user,
            shipping_address=ADDRESS,
            idempotency_key="db-unique-key",
        )
        with self.assertRaises(Exception):
            CheckoutIdempotencyRecord.objects.create(
                user=self.user,
                key="db-unique-key",
                request_fingerprint="abc",
            )

    def test_retry_after_failure_can_succeed(self):
        """
        A failed checkout rolls the claim back, so the same key can be reused
        after the cart is corrected.
        """
        self.variant.stock = 0
        self.variant.save()
        add_item(self.user, self.variant.pk, 1)
        with self.assertRaises(Exception):
            checkout_cart(
                user=self.user,
                shipping_address=ADDRESS,
                idempotency_key="retry-after-fail",
            )
        self.assertEqual(CheckoutIdempotencyRecord.objects.count(), 0)

        self.variant.stock = 5
        self.variant.save()
        order = checkout_cart(
            user=self.user,
            shipping_address=ADDRESS,
            idempotency_key="retry-after-fail",
        )
        self.assertEqual(order.items.count(), 1)

    def test_http_replay_does_not_create_second_order(self):
        add_item(self.user, self.variant.pk, 1)
        payload = {
            "idempotency_key": "http-replay",
            "shipping_address": ADDRESS,
        }
        first = self._auth().post(CHECKOUT_URL, payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        # Cart is already converted; replay must still return the original order.
        second = self._auth().post(CHECKOUT_URL, payload, format="json")
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(Order.objects.filter(user=self.user).count(), 1)
        self.assertEqual(
            Cart.objects.filter(user=self.user, status=Cart.Status.CHECKED_OUT).count(),
            1,
        )
