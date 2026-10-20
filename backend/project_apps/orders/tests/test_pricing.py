from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from project_apps.orders.pricing import (
    ZERO,
    calculate_line_total,
    calculate_order_totals,
    get_effective_unit_price,
    quantize_money,
)
from project_apps.orders.tests.helpers import OrdersTestCase


class PricingUnitTests(TestCase):
    def test_subtotal_sums_lines(self):
        totals = calculate_order_totals(
            [Decimal("10.00"), Decimal("2.50")],
        )
        self.assertEqual(totals.subtotal, Decimal("12.50"))
        self.assertEqual(totals.total, Decimal("12.50"))
        self.assertEqual(totals.shipping_fee, ZERO)

    def test_shipping_and_tax_added(self):
        totals = calculate_order_totals(
            [Decimal("10.00")],
            shipping_fee=Decimal("3.00"),
            tax_amount=Decimal("1.50"),
        )
        self.assertEqual(totals.total, Decimal("14.50"))

    def test_discount_subtracted(self):
        totals = calculate_order_totals(
            [Decimal("10.00")],
            discount_amount=Decimal("2.00"),
        )
        self.assertEqual(totals.total, Decimal("8.00"))

    def test_rounding_half_up(self):
        self.assertEqual(quantize_money(Decimal("1.225")), Decimal("1.23"))
        self.assertEqual(quantize_money(Decimal("1.224")), Decimal("1.22"))

    def test_line_total(self):
        self.assertEqual(
            calculate_line_total(Decimal("29.99"), 3),
            Decimal("89.97"),
        )

    def test_negative_total_rejected(self):
        with self.assertRaises(ValueError):
            calculate_order_totals(
                [Decimal("1.00")],
                discount_amount=Decimal("5.00"),
            )

    def test_negative_component_rejected(self):
        with self.assertRaises(ValueError):
            calculate_order_totals([Decimal("1.00")], shipping_fee=Decimal("-1.00"))


class EffectivePriceTests(OrdersTestCase):
    def test_list_price_without_discount(self):
        self.assertEqual(get_effective_unit_price(self.variant), Decimal("29.99"))

    def test_discount_window(self):
        now = timezone.now()
        self.variant.discount_price = Decimal("19.99")
        self.variant.discount_start = now - timezone.timedelta(hours=1)
        self.variant.discount_end = now + timezone.timedelta(hours=1)
        self.variant.save()
        self.assertEqual(get_effective_unit_price(self.variant), Decimal("19.99"))

    def test_expired_discount_uses_list_price(self):
        now = timezone.now()
        self.variant.discount_price = Decimal("19.99")
        self.variant.discount_start = now - timezone.timedelta(days=2)
        self.variant.discount_end = now - timezone.timedelta(days=1)
        self.variant.save()
        self.assertEqual(get_effective_unit_price(self.variant), Decimal("29.99"))
