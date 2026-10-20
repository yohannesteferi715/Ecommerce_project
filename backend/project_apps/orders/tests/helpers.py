from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from project_apps.cart.services import add_item
from project_apps.products.models import Category, Product, ProductVariant

User = get_user_model()

CHECKOUT_URL = "/api/checkout/"
ORDERS_URL = "/api/orders/"

ADDRESS = {
    "full_name": "Alice Example",
    "line1": "1 High Street",
    "city": "London",
    "postal_code": "SW1A 1AA",
    "country": "GB",
}


def order_url(pk) -> str:
    return f"/api/orders/{pk}/"


def cancel_url(pk) -> str:
    return f"/api/orders/{pk}/cancel/"


class OrdersFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="alice@example.com",
            full_name="Alice",
            password="testpass123",
        )
        cls.other_user = User.objects.create_user(
            email="bob@example.com",
            full_name="Bob",
            password="testpass123",
        )
        cls.staff_user = User.objects.create_user(
            email="staff@example.com",
            full_name="Staff",
            password="testpass123",
            is_staff=True,
        )
        cls.category = Category.objects.create(
            name="Order Test Category",
            slug="order-test-category",
            description="Orders tests",
        )
        cls.product = Product.objects.create(
            name="Order Test Product",
            slug="order-test-product",
            category=cls.category,
            is_active=True,
        )
        cls.variant = ProductVariant.objects.create(
            product=cls.product,
            sku="ORD-TEST-001",
            price=Decimal("29.99"),
            stock=100,
            is_active=True,
        )
        cls.variant2 = ProductVariant.objects.create(
            product=cls.product,
            sku="ORD-TEST-002",
            price=Decimal("49.99"),
            stock=50,
            is_active=True,
        )

    def setUp(self):
        self.client = APIClient()

    def _access_token(self, user) -> str:
        return str(RefreshToken.for_user(user).access_token)

    def _auth(self, user=None) -> APIClient:
        self.client.cookies["access_token"] = self._access_token(user or self.user)
        return self.client

    def _unauth(self) -> APIClient:
        self.client.cookies.clear()
        return self.client

    def _fill_cart(self, user=None, variant=None, quantity=1):
        return add_item(user or self.user, (variant or self.variant).pk, quantity)


class OrdersTestCase(OrdersFixtureMixin, TestCase):
    pass


class OrdersTransactionTestCase(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="alice@example.com",
            full_name="Alice",
            password="testpass123",
        )
        self.other_user = User.objects.create_user(
            email="bob@example.com",
            full_name="Bob",
            password="testpass123",
        )
        self.category = Category.objects.create(
            name="Order Test Category",
            slug="order-test-category",
            description="Orders tests",
        )
        self.product = Product.objects.create(
            name="Order Test Product",
            slug="order-test-product",
            category=self.category,
            is_active=True,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku="ORD-TEST-001",
            price=Decimal("29.99"),
            stock=1,
            is_active=True,
        )
        self.client = APIClient()

    def fill_cart(self, user, variant, quantity=1):
        return add_item(user, variant.pk, quantity)
