from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase

from project_apps.orders.models import Order, OrderItem, generate_order_number
from project_apps.orders.tests.helpers import ADDRESS, OrdersTestCase


class OrderModelTests(OrdersTestCase):
    def _make_order(self, **overrides) -> Order:
        fields = dict(
            user=self.user,
            order_number=generate_order_number(),
            subtotal=Decimal("29.99"),
            shipping_fee=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            total=Decimal("29.99"),
            currency="USD",
            shipping_address=ADDRESS,
        )
        fields.update(overrides)
        return Order.objects.create(**fields)

    def test_order_creation(self):
        order = self._make_order()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.payment_status, Order.PaymentStatus.UNPAID)
        self.assertEqual(order.fulfillment_status, Order.FulfillmentStatus.UNFULFILLED)
        self.assertTrue(order.order_number.startswith("ORD-"))

    def test_order_item_creation_and_snapshot(self):
        order = self._make_order()
        item = OrderItem.objects.create(
            order=order,
            variant=self.variant,
            product_name="Snap Name",
            sku="SNAP-SKU",
            unit_price=Decimal("10.00"),
            quantity=2,
            line_total=Decimal("20.00"),
        )
        self.variant.price = Decimal("99.00")
        self.variant.save()
        item.refresh_from_db()
        self.assertEqual(item.product_name, "Snap Name")
        self.assertEqual(item.sku, "SNAP-SKU")
        self.assertEqual(item.unit_price, Decimal("10.00"))

    def test_unique_order_numbers(self):
        self._make_order(order_number="ORD-TEST-UNIQUE-1")
        with self.assertRaises(IntegrityError):
            self._make_order(order_number="ORD-TEST-UNIQUE-1")

    def test_negative_total_rejected(self):
        with self.assertRaises(IntegrityError):
            self._make_order(total=Decimal("-1.00"), subtotal=Decimal("0.00"))

    def test_total_formula_constraint(self):
        with self.assertRaises(IntegrityError):
            self._make_order(
                subtotal=Decimal("10.00"),
                shipping_fee=Decimal("1.00"),
                tax_amount=Decimal("0.00"),
                discount_amount=Decimal("0.00"),
                total=Decimal("10.00"),
            )

    def test_zero_quantity_rejected(self):
        order = self._make_order()
        with self.assertRaises(IntegrityError):
            OrderItem.objects.create(
                order=order,
                variant=self.variant,
                product_name="X",
                sku="X",
                unit_price=Decimal("1.00"),
                quantity=0,
                line_total=Decimal("0.00"),
            )

    def test_negative_unit_price_rejected(self):
        order = self._make_order()
        with self.assertRaises(IntegrityError):
            OrderItem.objects.create(
                order=order,
                variant=self.variant,
                product_name="X",
                sku="X",
                unit_price=Decimal("-1.00"),
                quantity=1,
                line_total=Decimal("0.00"),
            )

    def test_unique_variant_per_order(self):
        order = self._make_order()
        OrderItem.objects.create(
            order=order,
            variant=self.variant,
            product_name="A",
            sku="A",
            unit_price=Decimal("1.00"),
            quantity=1,
            line_total=Decimal("1.00"),
        )
        with self.assertRaises(IntegrityError):
            OrderItem.objects.create(
                order=order,
                variant=self.variant,
                product_name="A",
                sku="A",
                unit_price=Decimal("1.00"),
                quantity=1,
                line_total=Decimal("1.00"),
            )

    def test_user_protect_prevents_delete(self):
        self._make_order()
        with self.assertRaises(Exception):
            self.user.delete()

    def test_valid_status_choices(self):
        order = self._make_order()
        for value, _ in Order.Status.choices:
            order.status = value
            order.save(update_fields=["status"])
        for value, _ in Order.PaymentStatus.choices:
            order.payment_status = value
            order.save(update_fields=["payment_status"])


class GenerateOrderNumberTests(TestCase):
    def test_format(self):
        number = generate_order_number()
        self.assertRegex(number, r"^ORD-\d{8}-[A-F0-9]{8}$")
