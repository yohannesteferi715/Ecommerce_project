from rest_framework import status

from project_apps.cart.services import add_item
from project_apps.orders.exceptions import (
    InvalidTransition,
    OrderAlreadyCancelled,
    OrderNotCancellable,
    OrderNotFound,
)
from project_apps.orders.models import Order
from project_apps.orders.services import (
    cancel_order,
    checkout_cart,
    record_verified_payment_result,
    transition_fulfillment_status,
    transition_order_status,
)
from project_apps.orders.tests.helpers import (
    ADDRESS,
    ORDERS_URL,
    OrdersTestCase,
    cancel_url,
    order_url,
)


class LifecycleTests(OrdersTestCase):
    def _order(self) -> Order:
        add_item(self.user, self.variant.pk, 2)
        return checkout_cart(
            user=self.user,
            shipping_address=ADDRESS,
            idempotency_key="lifecycle-order",
        )

    def test_valid_pending_to_confirmed_via_payment(self):
        order = self._order()
        updated = record_verified_payment_result(
            order_id=order.pk, result=Order.PaymentStatus.PAID
        )
        self.assertEqual(updated.status, Order.Status.CONFIRMED)
        self.assertEqual(updated.payment_status, Order.PaymentStatus.PAID)

    def test_payment_failure_does_not_delete_order(self):
        order = self._order()
        updated = record_verified_payment_result(
            order_id=order.pk, result=Order.PaymentStatus.FAILED
        )
        self.assertEqual(updated.status, Order.Status.PENDING)
        self.assertEqual(updated.payment_status, Order.PaymentStatus.FAILED)
        self.assertTrue(Order.objects.filter(pk=order.pk).exists())

    def test_refund_does_not_unfulfill(self):
        order = self._order()
        record_verified_payment_result(order_id=order.pk, result=Order.PaymentStatus.PAID)
        record_verified_payment_result(
            order_id=order.pk, result=Order.PaymentStatus.REFUNDED
        )
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.REFUNDED)
        self.assertEqual(order.fulfillment_status, Order.FulfillmentStatus.UNFULFILLED)
        self.assertNotEqual(order.status, Order.Status.CANCELLED)

    def test_invalid_transition(self):
        order = self._order()
        with self.assertRaises(InvalidTransition):
            transition_order_status(
                order_id=order.pk,
                user=self.staff_user,
                new_status=Order.Status.COMPLETED,
            )

    def test_customer_cannot_transition_own_order(self):
        order = self._order()
        with self.assertRaises(OrderNotFound):
            transition_order_status(
                order_id=order.pk,
                user=self.user,
                new_status=Order.Status.CONFIRMED,
            )

    def test_cancel_pending(self):
        order = self._order()
        cancelled = cancel_order(order_id=order.pk, user=self.user, reason="changed mind")
        self.assertEqual(cancelled.status, Order.Status.CANCELLED)
        self.assertIsNotNone(cancelled.cancelled_at)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 100)

    def test_duplicate_cancel_rejected_and_stock_not_double_restored(self):
        order = self._order()
        cancel_order(order_id=order.pk, user=self.user)
        self.variant.refresh_from_db()
        stock_after = self.variant.stock
        with self.assertRaises(OrderAlreadyCancelled):
            cancel_order(order_id=order.pk, user=self.user)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, stock_after)

    def test_cannot_cancel_completed(self):
        order = self._order()
        record_verified_payment_result(order_id=order.pk, result=Order.PaymentStatus.PAID)
        transition_order_status(
            order_id=order.pk,
            user=self.staff_user,
            new_status=Order.Status.PROCESSING,
        )
        transition_order_status(
            order_id=order.pk,
            user=self.staff_user,
            new_status=Order.Status.COMPLETED,
        )
        with self.assertRaises(OrderNotCancellable):
            cancel_order(order_id=order.pk, user=self.user)

    def test_paid_cancel_does_not_mark_refunded(self):
        order = self._order()
        record_verified_payment_result(order_id=order.pk, result=Order.PaymentStatus.PAID)
        cancelled = cancel_order(order_id=order.pk, user=self.user)
        self.assertEqual(cancelled.status, Order.Status.CANCELLED)
        self.assertEqual(cancelled.payment_status, Order.PaymentStatus.PAID)

    def test_http_list_and_detail(self):
        order = self._order()
        listing = self._auth().get(ORDERS_URL)
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(len(listing.json()), 1)
        self.assertNotIn("items", listing.json()[0])
        self.assertEqual(listing.json()[0]["item_count"], 1)

        detail = self._auth().get(order_url(order.pk))
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(len(detail.json()["items"]), 1)

    def test_cannot_list_other_users_orders(self):
        self._order()
        res = self._auth(self.other_user).get(ORDERS_URL)
        self.assertEqual(res.json(), [])

    def test_cannot_retrieve_other_users_order(self):
        order = self._order()
        res = self._auth(self.other_user).get(order_url(order.pk))
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_cancel_other_users_order(self):
        order = self._order()
        res = self._auth(self.other_user).post(cancel_url(order.pk), {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)

    def test_staff_can_cancel_other_users_order(self):
        order = self._order()
        cancelled = cancel_order(order_id=order.pk, user=self.staff_user, reason="admin")
        self.assertEqual(cancelled.status, Order.Status.CANCELLED)

    def test_unauthenticated_list(self):
        res = self._unauth().get(ORDERS_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cancel_http(self):
        order = self._order()
        res = self._auth().post(
            cancel_url(order.pk),
            {"reason": "not needed"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["status"], "cancelled")

    def test_service_hides_foreign_order_from_non_staff_transition(self):
        order = self._order()
        with self.assertRaises(OrderNotFound):
            transition_order_status(
                order_id=order.pk,
                user=self.other_user,
                new_status=Order.Status.CONFIRMED,
            )

    def test_fulfillment_advances_order_status(self):
        order = self._order()
        record_verified_payment_result(order_id=order.pk, result=Order.PaymentStatus.PAID)
        updated = transition_fulfillment_status(
            order_id=order.pk,
            user=self.staff_user,
            new_status=Order.FulfillmentStatus.PROCESSING,
        )
        self.assertEqual(updated.status, Order.Status.PROCESSING)
