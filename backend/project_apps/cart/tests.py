"""
Cart tests
==========
Run with:
    python manage.py test project_apps.cart --verbosity=2

Coverage areas
--------------
1.  Authentication & authorization
2.  Cart retrieval (empty and populated)
3.  Adding items — happy path, increment, availability validation
4.  Quantity limits
5.  Updating item quantity (set / replace)
6.  Removing items
7.  Clearing the cart
8.  Cross-customer isolation (ownership)
9.  Backend-authoritative pricing & totals
10. Price change reflected in cart response
11. DB-level uniqueness constraint on (cart, variant)
12. Concurrent cart-creation race (IntegrityError fallback path)
13. Concurrent add_item increment (atomic quantity accumulation)
14. Transaction rollback on failure inside atomic block

Authentication note
-------------------
The project uses CookieJWTAuthentication — tokens live in HttpOnly cookies,
not the Authorization header.  Every authenticated test call sets the cookie
via self.client.cookies.

Concurrency note
----------------
SQLite serialises all writes at the database level, so true parallel thread
tests cannot prove row-level lock behaviour.  The concurrency tests here
instead verify the *code paths* that handle races (the IntegrityError retry
in get_or_create_cart and the select_for_update in add_item) by simulating
the collision in a single thread via mocking.  This is documented in
services.py.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import call, patch, MagicMock

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase, override_settings

from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from project_apps.cart.models import Cart, CartItem
from project_apps.cart.services import (
    InvalidQuantity,
    ItemNotFound,
    ProductNotAvailable,
    add_item,
    clear_cart,
    get_cart_or_none,
    get_cart_totals,
    get_or_create_cart,
    remove_item,
    set_item_quantity,
)
from project_apps.products.models import Category, Product, ProductVariant

User = get_user_model()

# ---------------------------------------------------------------------------
# URL constants
# ---------------------------------------------------------------------------
CART_URL       = "/api/cart/"
CART_CLEAR_URL = "/api/cart/clear/"
CART_ITEMS_URL = "/api/cart/items/"


def item_url(pk: int) -> str:
    return f"/api/cart/items/{pk}/"


# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------

class CartTestBase(TestCase):
    """
    One-time fixture: two users + a small product catalog.
    Provides cookie-based JWT auth helpers.
    """

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

        cls.category = Category.objects.create(
            name="Test Category",
            slug="test-category",
            description="A test category",
        )
        cls.product = Product.objects.create(
            name="Test Product",
            slug="test-product",
            category=cls.category,
            is_active=True,
        )
        cls.variant = ProductVariant.objects.create(
            product=cls.product,
            sku="TEST-001",
            price=Decimal("29.99"),
            stock=100,
            is_active=True,
        )
        cls.variant2 = ProductVariant.objects.create(
            product=cls.product,
            sku="TEST-002",
            price=Decimal("49.99"),
            stock=50,
            is_active=True,
        )
        cls.inactive_variant = ProductVariant.objects.create(
            product=cls.product,
            sku="TEST-INACTIVE",
            price=Decimal("9.99"),
            stock=10,
            is_active=False,
        )
        cls.inactive_product = Product.objects.create(
            name="Inactive Product",
            slug="inactive-product",
            category=cls.category,
            is_active=False,
        )
        cls.inactive_product_variant = ProductVariant.objects.create(
            product=cls.inactive_product,
            sku="INACTIVE-PROD-001",
            price=Decimal("19.99"),
            stock=5,
            is_active=True,
        )

    def setUp(self):
        self.client = APIClient()

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _access_token(self, user) -> str:
        return str(RefreshToken.for_user(user).access_token)

    def _auth(self, user=None) -> APIClient:
        """Attach JWT access cookie for *user* (defaults to self.user)."""
        self.client.cookies["access_token"] = self._access_token(user or self.user)
        return self.client

    def _unauth(self) -> APIClient:
        self.client.cookies.clear()
        return self.client


# ===========================================================================
# 1. Authentication & authorization
# ===========================================================================

class AuthenticationTests(CartTestBase):

    def test_anonymous_get_cart_returns_401(self):
        self.assertEqual(
            self._unauth().get(CART_URL).status_code, status.HTTP_401_UNAUTHORIZED
        )

    def test_anonymous_add_item_returns_401(self):
        res = self._unauth().post(
            CART_ITEMS_URL, {"variant_id": self.variant.pk, "quantity": 1}
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_anonymous_clear_returns_401(self):
        self.assertEqual(
            self._unauth().delete(CART_CLEAR_URL).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_anonymous_patch_item_returns_401(self):
        self.assertEqual(
            self._unauth().patch(item_url(999), {"quantity": 1}).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_anonymous_delete_item_returns_401(self):
        self.assertEqual(
            self._unauth().delete(item_url(999)).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_authenticated_get_returns_200(self):
        self.assertEqual(
            self._auth().get(CART_URL).status_code, status.HTTP_200_OK
        )

    def test_get_cart_does_not_create_cart_record(self):
        """A GET by an authenticated user with no prior cart must not create one."""
        self._auth().get(CART_URL)
        self.assertEqual(Cart.objects.filter(user=self.user).count(), 0)

    def test_no_cart_created_for_anonymous_request(self):
        self._unauth().get(CART_URL)
        self.assertEqual(Cart.objects.count(), 0)


# ===========================================================================
# 2. Cart retrieval
# ===========================================================================

class CartRetrievalTests(CartTestBase):

    def test_empty_cart_shape(self):
        data = self._auth().get(CART_URL).json()
        self.assertIsNone(data["id"])
        self.assertEqual(data["items"], [])
        self.assertEqual(data["subtotal"], "0.00")
        self.assertEqual(data["item_count"], 0)
        self.assertEqual(data["total_units"], 0)

    def test_populated_cart_returns_items(self):
        add_item(self.user, self.variant.pk, 2)
        data = self._auth().get(CART_URL).json()
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["quantity"], 2)

    def test_cart_item_contains_variant_summary(self):
        add_item(self.user, self.variant.pk, 1)
        item = self._auth().get(CART_URL).json()["items"][0]
        self.assertEqual(item["variant"]["sku"], self.variant.sku)
        self.assertEqual(item["variant"]["product_id"], self.product.pk)

    def test_unit_price_and_line_total_in_response(self):
        add_item(self.user, self.variant.pk, 3)
        item = self._auth().get(CART_URL).json()["items"][0]
        self.assertEqual(Decimal(item["unit_price"]), self.variant.price)
        self.assertEqual(Decimal(item["line_total"]), self.variant.price * 3)

    def test_subtotal_sums_all_lines(self):
        add_item(self.user, self.variant.pk, 2)
        add_item(self.user, self.variant2.pk, 1)
        data = self._auth().get(CART_URL).json()
        expected = self.variant.price * 2 + self.variant2.price
        self.assertEqual(Decimal(data["subtotal"]), expected)

    def test_item_count_and_total_units(self):
        add_item(self.user, self.variant.pk, 3)
        add_item(self.user, self.variant2.pk, 2)
        data = self._auth().get(CART_URL).json()
        self.assertEqual(data["item_count"], 2)
        self.assertEqual(data["total_units"], 5)

    def test_availability_field_present_on_items(self):
        add_item(self.user, self.variant.pk, 1)
        item = self._auth().get(CART_URL).json()["items"][0]
        self.assertIn("availability", item)
        avail = item["availability"]
        self.assertIn("available", avail)
        self.assertIn("in_stock", avail)
        self.assertIn("is_active", avail)
        self.assertTrue(avail["available"])


# ===========================================================================
# 3. Adding items
# ===========================================================================

class AddItemTests(CartTestBase):

    def test_add_item_creates_cart_and_item(self):
        res = self._auth().post(
            CART_ITEMS_URL, {"variant_id": self.variant.pk, "quantity": 1}
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Cart.objects.filter(user=self.user).count(), 1)
        self.assertEqual(CartItem.objects.filter(cart__user=self.user).count(), 1)

    def test_add_item_response_shape(self):
        res = self._auth().post(
            CART_ITEMS_URL, {"variant_id": self.variant.pk, "quantity": 2}
        )
        data = res.json()
        for key in ("id", "variant", "quantity", "unit_price", "line_total", "availability"):
            self.assertIn(key, data, f"Missing key: {key}")
        self.assertEqual(data["quantity"], 2)

    def test_add_same_variant_increments_quantity(self):
        self._auth().post(CART_ITEMS_URL, {"variant_id": self.variant.pk, "quantity": 2})
        self._auth().post(CART_ITEMS_URL, {"variant_id": self.variant.pk, "quantity": 3})
        item = CartItem.objects.get(cart__user=self.user, variant=self.variant)
        self.assertEqual(item.quantity, 5)
        # Still only one row
        self.assertEqual(
            CartItem.objects.filter(cart__user=self.user, variant=self.variant).count(), 1
        )

    def test_add_different_variants_creates_separate_items(self):
        self._auth().post(CART_ITEMS_URL, {"variant_id": self.variant.pk, "quantity": 1})
        self._auth().post(CART_ITEMS_URL, {"variant_id": self.variant2.pk, "quantity": 1})
        self.assertEqual(CartItem.objects.filter(cart__user=self.user).count(), 2)

    def test_only_one_active_cart_created(self):
        self._auth().post(CART_ITEMS_URL, {"variant_id": self.variant.pk, "quantity": 1})
        self._auth().post(CART_ITEMS_URL, {"variant_id": self.variant2.pk, "quantity": 1})
        self.assertEqual(
            Cart.objects.filter(user=self.user, status=Cart.Status.ACTIVE).count(), 1
        )

    def test_add_inactive_variant_returns_400(self):
        res = self._auth().post(
            CART_ITEMS_URL, {"variant_id": self.inactive_variant.pk, "quantity": 1}
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", res.json())

    def test_add_variant_of_inactive_product_returns_400(self):
        res = self._auth().post(
            CART_ITEMS_URL,
            {"variant_id": self.inactive_product_variant.pk, "quantity": 1},
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_nonexistent_variant_returns_400(self):
        res = self._auth().post(CART_ITEMS_URL, {"variant_id": 999999, "quantity": 1})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_item_missing_variant_id_returns_400(self):
        res = self._auth().post(CART_ITEMS_URL, {"quantity": 1})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_item_missing_quantity_returns_400(self):
        res = self._auth().post(CART_ITEMS_URL, {"variant_id": self.variant.pk})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_inactive_variant_creates_no_cart(self):
        """A failed add must not leave a dangling empty Cart record."""
        self._auth().post(
            CART_ITEMS_URL, {"variant_id": self.inactive_variant.pk, "quantity": 1}
        )
        self.assertEqual(Cart.objects.filter(user=self.user).count(), 0)


# ===========================================================================
# 4. Quantity limits
# ===========================================================================

class QuantityLimitTests(CartTestBase):

    def test_zero_quantity_returns_400(self):
        res = self._auth().post(
            CART_ITEMS_URL, {"variant_id": self.variant.pk, "quantity": 0}
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_negative_quantity_returns_400(self):
        res = self._auth().post(
            CART_ITEMS_URL, {"variant_id": self.variant.pk, "quantity": -5}
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_exceeding_max_on_add_returns_400(self):
        res = self._auth().post(
            CART_ITEMS_URL, {"variant_id": self.variant.pk, "quantity": 100}
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_increment_beyond_max_returns_400_and_quantity_unchanged(self):
        add_item(self.user, self.variant.pk, 99)
        res = self._auth().post(
            CART_ITEMS_URL, {"variant_id": self.variant.pk, "quantity": 1}
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        item = CartItem.objects.get(cart__user=self.user, variant=self.variant)
        self.assertEqual(item.quantity, 99)

    def test_set_quantity_to_max_is_accepted(self):
        add_item(self.user, self.variant.pk, 1)
        item = CartItem.objects.get(cart__user=self.user, variant=self.variant)
        res = self._auth().patch(item_url(item.pk), {"quantity": 99})
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_set_quantity_above_max_returns_400(self):
        add_item(self.user, self.variant.pk, 1)
        item = CartItem.objects.get(cart__user=self.user, variant=self.variant)
        res = self._auth().patch(item_url(item.pk), {"quantity": 100})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_set_quantity_to_zero_returns_400(self):
        add_item(self.user, self.variant.pk, 1)
        item = CartItem.objects.get(cart__user=self.user, variant=self.variant)
        res = self._auth().patch(item_url(item.pk), {"quantity": 0})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


# ===========================================================================
# 5. Updating item quantity
# ===========================================================================

class UpdateItemTests(CartTestBase):

    def setUp(self):
        super().setUp()
        self.item = add_item(self.user, self.variant.pk, 3)

    def test_patch_sets_absolute_quantity(self):
        self._auth().patch(item_url(self.item.pk), {"quantity": 7})
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 7)

    def test_patch_replaces_not_accumulates(self):
        """Two PATCH calls each setting quantity=5 must leave quantity=5, not 10."""
        self._auth().patch(item_url(self.item.pk), {"quantity": 5})
        self._auth().patch(item_url(self.item.pk), {"quantity": 5})
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 5)

    def test_patch_returns_200_and_updated_quantity(self):
        res = self._auth().patch(item_url(self.item.pk), {"quantity": 7})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["quantity"], 7)

    def test_patch_response_contains_updated_line_total(self):
        res = self._auth().patch(item_url(self.item.pk), {"quantity": 4})
        self.assertEqual(Decimal(res.json()["line_total"]), self.variant.price * 4)

    def test_patch_nonexistent_item_returns_404(self):
        res = self._auth().patch(item_url(999999), {"quantity": 1})
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_without_quantity_returns_400(self):
        res = self._auth().patch(item_url(self.item.pk), {})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


# ===========================================================================
# 6. Removing items
# ===========================================================================

class RemoveItemTests(CartTestBase):

    def setUp(self):
        super().setUp()
        self.item  = add_item(self.user, self.variant.pk, 2)
        self.item2 = add_item(self.user, self.variant2.pk, 1)

    def test_delete_item_returns_204(self):
        res = self._auth().delete(item_url(self.item.pk))
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

    def test_delete_removes_only_target_item(self):
        self._auth().delete(item_url(self.item.pk))
        self.assertFalse(CartItem.objects.filter(pk=self.item.pk).exists())
        self.assertTrue(CartItem.objects.filter(pk=self.item2.pk).exists())

    def test_delete_nonexistent_item_returns_404(self):
        res = self._auth().delete(item_url(999999))
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_item_twice_returns_404_on_second(self):
        self._auth().delete(item_url(self.item.pk))
        res = self._auth().delete(item_url(self.item.pk))
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


# ===========================================================================
# 7. Clearing the cart
# ===========================================================================

class ClearCartTests(CartTestBase):

    def test_clear_returns_204(self):
        add_item(self.user, self.variant.pk, 1)
        res = self._auth().delete(CART_CLEAR_URL)
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

    def test_clear_removes_all_items(self):
        add_item(self.user, self.variant.pk, 2)
        add_item(self.user, self.variant2.pk, 3)
        self._auth().delete(CART_CLEAR_URL)
        self.assertEqual(CartItem.objects.filter(cart__user=self.user).count(), 0)

    def test_clear_empty_cart_returns_204(self):
        """Clear with no active cart is a no-op — must still return 204."""
        res = self._auth().delete(CART_CLEAR_URL)
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

    def test_clear_does_not_delete_cart_record(self):
        add_item(self.user, self.variant.pk, 1)
        self._auth().delete(CART_CLEAR_URL)
        self.assertTrue(
            Cart.objects.filter(user=self.user, status=Cart.Status.ACTIVE).exists()
        )

    def test_after_clear_get_cart_returns_empty_shape(self):
        add_item(self.user, self.variant.pk, 1)
        self._auth().delete(CART_CLEAR_URL)
        data = self._auth().get(CART_URL).json()
        self.assertEqual(data["items"], [])
        self.assertEqual(data["subtotal"], "0.00")


# ===========================================================================
# 8. Cross-customer isolation (ownership)
# ===========================================================================

class OwnershipTests(CartTestBase):

    def setUp(self):
        super().setUp()
        # alice adds an item
        self.alice_item = add_item(self.user, self.variant.pk, 2)
        self.alice_cart = Cart.objects.get(user=self.user, status=Cart.Status.ACTIVE)

    def test_bob_cannot_read_alices_cart_items(self):
        data = self._auth(self.other_user).get(CART_URL).json()
        self.assertEqual(data["items"], [])

    def test_bob_cannot_patch_alices_item(self):
        res = self._auth(self.other_user).patch(
            item_url(self.alice_item.pk), {"quantity": 10}
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_bob_cannot_delete_alices_item(self):
        res = self._auth(self.other_user).delete(item_url(self.alice_item.pk))
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_bob_clear_does_not_affect_alices_items(self):
        add_item(self.other_user, self.variant.pk, 1)
        self._auth(self.other_user).delete(CART_CLEAR_URL)
        self.assertEqual(
            CartItem.objects.filter(cart=self.alice_cart).count(), 1
        )

    def test_client_supplied_user_id_is_ignored(self):
        """Sending a user_id field must not let one customer access another's cart."""
        # Bob sends alice's user_id in the request body — should have no effect
        res = self._auth(self.other_user).post(
            CART_ITEMS_URL,
            {"variant_id": self.variant.pk, "quantity": 1, "user_id": self.user.pk},
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        # The new item must be in Bob's cart, not Alice's
        bob_cart = Cart.objects.get(user=self.other_user, status=Cart.Status.ACTIVE)
        self.assertTrue(CartItem.objects.filter(cart=bob_cart, variant=self.variant).exists())
        alice_items = CartItem.objects.filter(cart=self.alice_cart, variant=self.variant)
        self.assertEqual(alice_items.count(), 1)        # Alice's existing item unchanged
        self.assertEqual(alice_items.first().quantity, 2)  # quantity still 2, not incremented


# ===========================================================================
# 9. Backend-authoritative pricing & totals
# ===========================================================================

class PricingTests(CartTestBase):

    def test_unit_price_sourced_from_variant_not_client(self):
        """Client-supplied price fields must be silently ignored."""
        res = self._auth().post(
            CART_ITEMS_URL,
            {"variant_id": self.variant.pk, "quantity": 1, "price": "0.01"},
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(res.json()["unit_price"]), self.variant.price)

    def test_line_total_equals_unit_price_times_quantity(self):
        res = self._auth().post(
            CART_ITEMS_URL, {"variant_id": self.variant.pk, "quantity": 5}
        )
        data = res.json()
        self.assertEqual(
            Decimal(data["line_total"]),
            Decimal(data["unit_price"]) * data["quantity"],
        )

    def test_subtotal_equals_sum_of_line_totals(self):
        add_item(self.user, self.variant.pk, 3)
        add_item(self.user, self.variant2.pk, 2)
        data = self._auth().get(CART_URL).json()
        computed = sum(Decimal(i["line_total"]) for i in data["items"])
        self.assertEqual(Decimal(data["subtotal"]), computed)

    def test_price_change_reflected_immediately(self):
        """If the variant price changes, the cart must reflect the new price."""
        add_item(self.user, self.variant.pk, 2)

        # Simulate a price change
        self.variant.price = Decimal("39.99")
        self.variant.save(update_fields=["price"])

        data = self._auth().get(CART_URL).json()
        self.assertEqual(Decimal(data["items"][0]["unit_price"]), Decimal("39.99"))
        self.assertEqual(Decimal(data["items"][0]["line_total"]), Decimal("39.99") * 2)

        # Restore original price so other tests are unaffected
        self.variant.price = Decimal("29.99")
        self.variant.save(update_fields=["price"])

    def test_discount_price_used_when_window_is_active(self):
        from django.utils import timezone

        self.variant.discount_price = Decimal("19.99")
        self.variant.discount_start = timezone.now() - timezone.timedelta(hours=1)
        self.variant.discount_end   = timezone.now() + timezone.timedelta(hours=1)
        self.variant.save(update_fields=["discount_price", "discount_start", "discount_end"])

        add_item(self.user, self.variant.pk, 1)
        data = self._auth().get(CART_URL).json()
        self.assertEqual(Decimal(data["items"][0]["unit_price"]), Decimal("19.99"))

        # Restore
        self.variant.discount_price = None
        self.variant.discount_start = None
        self.variant.discount_end   = None
        self.variant.save(update_fields=["discount_price", "discount_start", "discount_end"])


# ===========================================================================
# 10. Product availability reflected on cart items
# ===========================================================================

class AvailabilityTests(CartTestBase):

    def test_in_stock_item_shows_available_true(self):
        add_item(self.user, self.variant.pk, 1)
        item = self._auth().get(CART_URL).json()["items"][0]
        self.assertTrue(item["availability"]["available"])
        self.assertTrue(item["availability"]["in_stock"])

    def test_zero_stock_item_shows_in_stock_false(self):
        self.variant.stock = 0
        self.variant.save(update_fields=["stock"])

        add_item(self.user, self.variant.pk, 1)
        item = self._auth().get(CART_URL).json()["items"][0]
        self.assertFalse(item["availability"]["in_stock"])
        self.assertFalse(item["availability"]["available"])

        # Restore
        self.variant.stock = 100
        self.variant.save(update_fields=["stock"])

    def test_deactivated_variant_shows_available_false(self):
        """Variant deactivated after being added shows is_active=False."""
        add_item(self.user, self.variant.pk, 1)
        self.variant.is_active = False
        self.variant.save(update_fields=["is_active"])

        item = self._auth().get(CART_URL).json()["items"][0]
        self.assertFalse(item["availability"]["is_active"])
        self.assertFalse(item["availability"]["available"])

        # Restore
        self.variant.is_active = True
        self.variant.save(update_fields=["is_active"])


# ===========================================================================
# 11. DB-level uniqueness constraints
# ===========================================================================

class DatabaseConstraintTests(CartTestBase):

    def test_unique_active_cart_per_user_constraint(self):
        """
        Directly creating two active carts for the same user must raise
        IntegrityError — the partial unique index is the enforcement point.
        """
        Cart.objects.create(user=self.user, status=Cart.Status.ACTIVE)
        with self.assertRaises(Exception):  # IntegrityError or db-level error
            Cart.objects.create(user=self.user, status=Cart.Status.ACTIVE)

    def test_multiple_checked_out_carts_allowed(self):
        """Non-active carts are not constrained — order history must be preserved."""
        Cart.objects.create(user=self.user, status=Cart.Status.CHECKED_OUT)
        Cart.objects.create(user=self.user, status=Cart.Status.CHECKED_OUT)
        self.assertEqual(
            Cart.objects.filter(user=self.user, status=Cart.Status.CHECKED_OUT).count(), 2
        )

    def test_unique_cart_item_variant_constraint(self):
        """
        Directly creating two CartItem rows for the same (cart, variant)
        must raise IntegrityError.
        """
        cart = get_or_create_cart(self.user)
        CartItem.objects.create(cart=cart, variant=self.variant, quantity=1)
        with self.assertRaises(Exception):
            CartItem.objects.create(cart=cart, variant=self.variant, quantity=2)


# ===========================================================================
# 12. Concurrent cart-creation race — IntegrityError fallback path
# ===========================================================================

class ConcurrentCartCreationTests(CartTestBase):

    def test_integrity_error_on_duplicate_insert_returns_existing_cart(self):
        """
        Simulate the race where get_or_create fires two concurrent INSERTs.
        The second writer gets IntegrityError; the service must recover by
        fetching the winner's cart rather than propagating the error.
        """
        # Pre-create the cart that 'won' the race
        existing = Cart.objects.create(user=self.user, status=Cart.Status.ACTIVE)

        original_get_or_create = Cart.objects.get_or_create

        call_count = {"n": 0}

        def mock_get_or_create(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # First call: raise IntegrityError to simulate the losing writer
                raise IntegrityError("duplicate key")
            return original_get_or_create(**kwargs)

        with patch.object(Cart.objects, "get_or_create", side_effect=mock_get_or_create):
            cart = get_or_create_cart(self.user)

        self.assertEqual(cart.pk, existing.pk)

    def test_get_or_create_cart_is_idempotent(self):
        """Calling get_or_create_cart twice returns the same cart."""
        cart1 = get_or_create_cart(self.user)
        cart2 = get_or_create_cart(self.user)
        self.assertEqual(cart1.pk, cart2.pk)
        self.assertEqual(Cart.objects.filter(user=self.user, status=Cart.Status.ACTIVE).count(), 1)


# ===========================================================================
# 13. Concurrent add_item — atomic quantity accumulation
# ===========================================================================

class ConcurrentAddItemTests(CartTestBase):

    def test_sequential_add_accumulates_correctly(self):
        """
        Baseline: sequential calls to add_item accumulate quantity correctly.
        This verifies the read-then-write path works correctly end-to-end.
        """
        add_item(self.user, self.variant.pk, 5)
        add_item(self.user, self.variant.pk, 3)
        item = CartItem.objects.get(cart__user=self.user, variant=self.variant)
        self.assertEqual(item.quantity, 8)

    def test_add_item_uses_select_for_update(self):
        """
        Verify that add_item issues a SELECT FOR UPDATE when the item already
        exists, not just a plain SELECT.  We check this by confirming the
        select_for_update queryset method is called inside the atomic block.
        """
        cart = get_or_create_cart(self.user)
        CartItem.objects.create(cart=cart, variant=self.variant, quantity=1)

        original_qs_method = CartItem.objects.select_for_update

        select_for_update_called = {"called": False}

        def tracking_select_for_update(*args, **kwargs):
            select_for_update_called["called"] = True
            return original_qs_method(*args, **kwargs)

        with patch.object(
            CartItem.objects, "select_for_update", side_effect=tracking_select_for_update
        ):
            add_item(self.user, self.variant.pk, 2)

        self.assertTrue(
            select_for_update_called["called"],
            "add_item must call select_for_update() when incrementing an existing item",
        )
        item = CartItem.objects.get(cart=cart, variant=self.variant)
        self.assertEqual(item.quantity, 3)


# ===========================================================================
# 14. Service-layer unit tests
# ===========================================================================

class ServiceUnitTests(CartTestBase):
    """Direct service function tests — bypasses HTTP layer."""

    def test_get_cart_or_none_returns_none_before_first_add(self):
        self.assertIsNone(get_cart_or_none(self.user))

    def test_get_cart_or_none_returns_cart_after_add(self):
        add_item(self.user, self.variant.pk, 1)
        self.assertIsNotNone(get_cart_or_none(self.user))

    def test_add_item_raises_product_not_available_for_inactive_variant(self):
        with self.assertRaises(ProductNotAvailable):
            add_item(self.user, self.inactive_variant.pk, 1)

    def test_add_item_raises_invalid_quantity_for_zero(self):
        with self.assertRaises(InvalidQuantity):
            add_item(self.user, self.variant.pk, 0)

    def test_add_item_raises_invalid_quantity_for_negative(self):
        with self.assertRaises(InvalidQuantity):
            add_item(self.user, self.variant.pk, -1)

    def test_set_item_quantity_raises_item_not_found_for_wrong_user(self):
        item = add_item(self.user, self.variant.pk, 2)
        with self.assertRaises(ItemNotFound):
            set_item_quantity(self.other_user, item.pk, 5)

    def test_remove_item_raises_item_not_found_for_wrong_user(self):
        item = add_item(self.user, self.variant.pk, 2)
        with self.assertRaises(ItemNotFound):
            remove_item(self.other_user, item.pk)

    def test_clear_cart_returns_zero_when_no_cart(self):
        self.assertEqual(clear_cart(self.user), 0)

    def test_clear_cart_returns_count_of_deleted_items(self):
        add_item(self.user, self.variant.pk, 1)
        add_item(self.user, self.variant2.pk, 1)
        count = clear_cart(self.user)
        self.assertEqual(count, 2)

    def test_get_cart_totals_empty_cart(self):
        cart = get_or_create_cart(self.user)
        totals = get_cart_totals(cart)
        self.assertEqual(totals["subtotal"], Decimal("0.00"))
        self.assertEqual(totals["item_count"], 0)
        self.assertEqual(totals["total_units"], 0)

    def test_get_cart_totals_with_items(self):
        add_item(self.user, self.variant.pk, 2)
        add_item(self.user, self.variant2.pk, 3)
        cart = Cart.objects.get(user=self.user, status=Cart.Status.ACTIVE)
        totals = get_cart_totals(cart)
        expected = self.variant.price * 2 + self.variant2.price * 3
        self.assertEqual(totals["subtotal"], expected)
        self.assertEqual(totals["item_count"], 2)
        self.assertEqual(totals["total_units"], 5)

    def test_add_nonexistent_variant_raises_product_not_available(self):
        with self.assertRaises(ProductNotAvailable):
            add_item(self.user, 999999, 1)

    @override_settings(MAX_CART_ITEM_QUANTITY=5)
    def test_max_qty_setting_is_respected(self):
        with self.assertRaises(InvalidQuantity):
            add_item(self.user, self.variant.pk, 6)
