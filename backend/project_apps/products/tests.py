"""
Tests for the seed_products management command.

Run with:
    python manage.py test project_apps.products.tests
    # or, from the backend directory:
    python manage.py test project_apps.products
"""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from project_apps.products.models import (
    Attribute,
    AttributeValue,
    Category,
    Product,
    ProductVariant,
    ProductVariantAttribute,
    Tag,
)
from project_apps.products.management.commands.seed_products import (
    ATTRIBUTES,
    CATEGORIES,
    PRODUCTS,
    TAGS,
)


def _run_seed(**kwargs) -> tuple[str, str]:
    """Call seed_products and return (stdout, stderr) as strings."""
    out, err = StringIO(), StringIO()
    call_command("seed_products", stdout=out, stderr=err, **kwargs)
    return out.getvalue(), err.getvalue()


class SeedInitialRunTest(TestCase):
    """Verify that a fresh run creates the expected number of records."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.stdout, cls.stderr = _run_seed(verbosity=0)

    # --- Categories --------------------------------------------------------

    def test_all_categories_created(self):
        self.assertEqual(Category.objects.count(), len(CATEGORIES))

    def test_top_level_categories_have_no_parent(self):
        top_level_names = [name for name, parent, *_ in CATEGORIES if parent is None]
        qs = Category.objects.filter(parent__isnull=True)
        self.assertEqual(qs.count(), len(top_level_names))

    def test_child_categories_have_correct_parent(self):
        child_entries = [(name, parent) for name, parent, *_ in CATEGORIES if parent]
        for child_name, parent_name in child_entries:
            child = Category.objects.get(name=child_name)
            self.assertIsNotNone(child.parent, f"'{child_name}' should have a parent")
            self.assertEqual(
                child.parent.name, parent_name,
                f"'{child_name}' parent should be '{parent_name}'"
            )

    def test_category_slugs_are_populated(self):
        for cat in Category.objects.all():
            self.assertTrue(cat.slug, f"Category '{cat.name}' has an empty slug")

    def test_categories_are_active_by_default(self):
        self.assertEqual(
            Category.objects.filter(is_active=True).count(),
            len(CATEGORIES),
        )

    # --- Tags --------------------------------------------------------------

    def test_all_tags_created(self):
        self.assertEqual(Tag.objects.count(), len(TAGS))

    def test_tag_slugs_match_definitions(self):
        for name, slug in TAGS:
            self.assertTrue(
                Tag.objects.filter(slug=slug).exists(),
                f"Tag with slug '{slug}' not found",
            )

    # --- Attributes --------------------------------------------------------

    def test_all_attributes_created(self):
        self.assertEqual(Attribute.objects.count(), len(ATTRIBUTES))

    def test_attribute_values_count(self):
        expected_total = sum(len(vals) for _, vals in ATTRIBUTES)
        self.assertEqual(AttributeValue.objects.count(), expected_total)

    def test_attribute_values_linked_to_correct_attribute(self):
        for attr_name, values in ATTRIBUTES:
            attr = Attribute.objects.get(name=attr_name)
            self.assertEqual(
                attr.values.count(),
                len(values),
                f"Attribute '{attr_name}' should have {len(values)} values",
            )

    def test_unique_together_constraint_satisfied(self):
        """No (attribute, value) pair should appear twice."""
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT attribute_id, value, COUNT(*) as cnt "
                "FROM products_attributevalue "
                "GROUP BY attribute_id, value "
                "HAVING cnt > 1"
            )
            duplicates = cursor.fetchall()
        self.assertEqual(duplicates, [], f"Duplicate AttributeValues found: {duplicates}")

    # --- Products ----------------------------------------------------------

    def test_all_products_created(self):
        self.assertEqual(Product.objects.count(), len(PRODUCTS))

    def test_products_are_active(self):
        self.assertEqual(
            Product.objects.filter(is_active=True).count(),
            len(PRODUCTS),
        )

    def test_product_slugs_are_populated(self):
        for product in Product.objects.all():
            self.assertTrue(product.slug, f"Product '{product.name}' has an empty slug")

    def test_product_slug_uniqueness(self):
        slugs = list(Product.objects.values_list("slug", flat=True))
        self.assertEqual(len(slugs), len(set(slugs)), "Duplicate product slugs detected")

    def test_products_have_categories(self):
        for product in Product.objects.all():
            self.assertIsNotNone(
                product.category,
                f"Product '{product.name}' has no category",
            )

    def test_products_have_tags(self):
        for data in PRODUCTS:
            if data.get("tags"):
                product = Product.objects.get(name=data["name"])
                self.assertGreater(
                    product.tags.count(), 0,
                    f"Product '{data['name']}' should have at least one tag",
                )

    # --- Variants ----------------------------------------------------------

    def test_variants_created(self):
        expected = sum(len(d["variants"]) for d in PRODUCTS)
        self.assertEqual(ProductVariant.objects.count(), expected)

    def test_variant_skus_are_unique(self):
        skus = list(ProductVariant.objects.values_list("sku", flat=True))
        self.assertEqual(len(skus), len(set(skus)), "Duplicate variant SKUs detected")

    def test_variant_prices_are_positive(self):
        from decimal import Decimal
        zero = Decimal("0.00")
        for v in ProductVariant.objects.all():
            self.assertGreater(v.price, zero, f"Variant {v.sku} has non-positive price")

    def test_variants_linked_to_correct_product(self):
        for data in PRODUCTS:
            product = Product.objects.get(name=data["name"])
            expected_skus = {v["sku"] for v in data["variants"]}
            actual_skus   = set(product.variants.values_list("sku", flat=True))
            self.assertEqual(
                actual_skus, expected_skus,
                f"Variant SKUs mismatch for product '{data['name']}'",
            )

    # --- Variant Attributes ------------------------------------------------

    def test_variant_attributes_created(self):
        expected = sum(
            len(v.get("attributes", []))
            for d in PRODUCTS
            for v in d["variants"]
        )
        self.assertEqual(ProductVariantAttribute.objects.count(), expected)

    def test_variant_attribute_uniqueness(self):
        """No (variant, attribute, value) triple should appear twice."""
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT variant_id, attribute_id, value_id, COUNT(*) as cnt "
                "FROM products_productvariantattribute "
                "GROUP BY variant_id, attribute_id, value_id "
                "HAVING cnt > 1"
            )
            duplicates = cursor.fetchall()
        self.assertEqual(duplicates, [], f"Duplicate ProductVariantAttributes: {duplicates}")

    def test_variant_attribute_values_belong_to_correct_attribute(self):
        """Each ProductVariantAttribute.value must belong to the same attribute."""
        for pva in ProductVariantAttribute.objects.select_related("attribute", "value"):
            self.assertEqual(
                pva.value.attribute_id,
                pva.attribute_id,
                f"PVA pk={pva.pk}: value '{pva.value.value}' does not belong "
                f"to attribute '{pva.attribute.name}'",
            )

    # --- Discount window ---------------------------------------------------

    def test_discounted_variants_have_date_window(self):
        discounted = ProductVariant.objects.filter(discount_price__isnull=False)
        self.assertGreater(discounted.count(), 0, "Expected at least one discounted variant")
        for v in discounted:
            self.assertIsNotNone(v.discount_start, f"Variant {v.sku} missing discount_start")
            self.assertIsNotNone(v.discount_end,   f"Variant {v.sku} missing discount_end")
            self.assertLess(
                v.discount_start, v.discount_end,
                f"Variant {v.sku}: discount_start must be before discount_end",
            )

    def test_non_discounted_variants_have_no_date_window(self):
        non_discounted = ProductVariant.objects.filter(discount_price__isnull=True)
        for v in non_discounted:
            self.assertIsNone(v.discount_start, f"Variant {v.sku} should have no discount_start")
            self.assertIsNone(v.discount_end,   f"Variant {v.sku} should have no discount_end")


class SeedIdempotencyTest(TestCase):
    """Verify that running seed_products twice produces no duplicates."""

    def test_double_run_no_duplicates(self):
        _run_seed(verbosity=0)
        _run_seed(verbosity=0)

        self.assertEqual(Category.objects.count(),      len(CATEGORIES))
        self.assertEqual(Tag.objects.count(),           len(TAGS))
        self.assertEqual(Attribute.objects.count(),     len(ATTRIBUTES))
        self.assertEqual(
            AttributeValue.objects.count(),
            sum(len(v) for _, v in ATTRIBUTES),
        )
        self.assertEqual(Product.objects.count(),       len(PRODUCTS))
        self.assertEqual(
            ProductVariant.objects.count(),
            sum(len(d["variants"]) for d in PRODUCTS),
        )
        self.assertEqual(
            ProductVariantAttribute.objects.count(),
            sum(
                len(v.get("attributes", []))
                for d in PRODUCTS
                for v in d["variants"]
            ),
        )

    def test_triple_run_stable(self):
        for _ in range(3):
            _run_seed(verbosity=0)
        self.assertEqual(Product.objects.count(), len(PRODUCTS))
        self.assertEqual(ProductVariant.objects.count(),
                         sum(len(d["variants"]) for d in PRODUCTS))


class SeedExistingRecordsTest(TestCase):
    """Verify that pre-existing records are handled correctly."""

    def test_pre_existing_category_not_duplicated(self):
        # Create a category with the same slug the seeder would use
        Category.objects.create(
            name="Electronics",
            slug="electronics",
            description="Pre-existing electronics category.",
        )
        _run_seed(verbosity=0)
        self.assertEqual(Category.objects.filter(name="Electronics").count(), 1)

    def test_pre_existing_tag_not_duplicated(self):
        Tag.objects.create(name="Best Seller", slug="best-seller")
        _run_seed(verbosity=0)
        self.assertEqual(Tag.objects.filter(slug="best-seller").count(), 1)

    def test_pre_existing_product_not_duplicated(self):
        # Need category first so the product FK resolves
        _run_seed(verbosity=0)
        _run_seed(verbosity=0)
        self.assertEqual(Product.objects.count(), len(PRODUCTS))


class SeedRelationshipsTest(TestCase):
    """Verify referential integrity across all seeded models."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _run_seed(verbosity=0)

    def test_child_categories_parent_fk_valid(self):
        for cat in Category.objects.filter(parent__isnull=False):
            # Will raise if parent PK doesn't resolve
            self.assertIsNotNone(Category.objects.get(pk=cat.parent_id))

    def test_all_products_category_fk_valid(self):
        for product in Product.objects.all():
            self.assertIsNotNone(Category.objects.get(pk=product.category_id))

    def test_all_variants_product_fk_valid(self):
        for v in ProductVariant.objects.all():
            self.assertIsNotNone(Product.objects.get(pk=v.product_id))

    def test_all_pva_fks_valid(self):
        for pva in ProductVariantAttribute.objects.all():
            self.assertIsNotNone(ProductVariant.objects.get(pk=pva.variant_id))
            self.assertIsNotNone(Attribute.objects.get(pk=pva.attribute_id))
            self.assertIsNotNone(AttributeValue.objects.get(pk=pva.value_id))

    def test_clothing_products_in_clothing_subtree(self):
        clothing_cat = Category.objects.get(slug="clothing")
        child_ids = set(
            Category.objects.filter(parent=clothing_cat).values_list("id", flat=True)
        )
        child_ids.add(clothing_cat.pk)
        clothing_products = Product.objects.filter(category_id__in=child_ids)
        self.assertGreater(clothing_products.count(), 0)

    def test_electronics_products_in_electronics_subtree(self):
        electronics_cat = Category.objects.get(slug="electronics")
        child_ids = set(
            Category.objects.filter(parent=electronics_cat).values_list("id", flat=True)
        )
        child_ids.add(electronics_cat.pk)
        elec_products = Product.objects.filter(category_id__in=child_ids)
        self.assertGreater(elec_products.count(), 0)


class SeedDryRunTest(TestCase):
    """Verify that --dry-run commits nothing to the database."""

    def test_dry_run_creates_no_records(self):
        _run_seed(dry_run=True, verbosity=0)

        self.assertEqual(Category.objects.count(),              0)
        self.assertEqual(Tag.objects.count(),                   0)
        self.assertEqual(Attribute.objects.count(),             0)
        self.assertEqual(AttributeValue.objects.count(),        0)
        self.assertEqual(Product.objects.count(),               0)
        self.assertEqual(ProductVariant.objects.count(),        0)
        self.assertEqual(ProductVariantAttribute.objects.count(), 0)

    def test_dry_run_output_contains_warning(self):
        stdout, _ = _run_seed(dry_run=True, verbosity=0)
        self.assertIn("DRY RUN", stdout)

    def test_dry_run_then_real_run_creates_records(self):
        _run_seed(dry_run=True, verbosity=0)
        _run_seed(verbosity=0)
        self.assertEqual(Product.objects.count(), len(PRODUCTS))

    def test_dry_run_after_real_run_leaves_data_intact(self):
        _run_seed(verbosity=0)
        product_count = Product.objects.count()
        _run_seed(dry_run=True, verbosity=0)
        # Real data must be untouched after dry-run
        self.assertEqual(Product.objects.count(), product_count)
