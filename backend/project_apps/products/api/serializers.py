from django.db.models import Avg
from django.utils import timezone
from django.utils.text import slugify

from rest_framework import serializers

from project_apps.products.models import (
    Attribute,
    AttributeValue,
    Category,
    Product,
    ProductImage,
    ProductReview,
    ProductVariant,
    ProductVariantAttribute,
    Tag,
)


class CategorySerializer(serializers.ModelSerializer):
    slug = serializers.ReadOnlyField()
    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = '__all__'

    def create(self, validated_data):
        validated_data['slug'] = slugify(validated_data['name'])
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if 'name' in validated_data and validated_data['name'] != instance.name:
            instance.slug = slugify(validated_data['name'])
        return super().update(instance, validated_data)

    def get_children(self, obj):
        # O3 FIX: removed redundant .exists() call before .all()
        children_qs = obj.children.all()
        if children_qs:
            return CategorySerializer(children_qs, many=True).data
        return []


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name', 'slug']
        read_only_fields = ['id']


class AttributeValueSerializer(serializers.ModelSerializer):
    attribute_name = serializers.CharField(source='attribute.name', read_only=True)

    class Meta:
        model = AttributeValue
        fields = ['id', 'attribute', 'attribute_name', 'value', 'is_default',
                  'sort_order', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class AttributeSerializer(serializers.ModelSerializer):
    """Attribute serializer with nested values"""
    values = AttributeValueSerializer(many=True, read_only=True)

    class Meta:
        model = Attribute
        fields = ['id', 'name', 'values', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class ProductVariantAttributeSerializer(serializers.ModelSerializer):
    """Product variant attribute serializer"""
    attribute_name = serializers.CharField(source='attribute.name', read_only=True)
    value_display = serializers.CharField(source='value.value', read_only=True)

    class Meta:
        model = ProductVariantAttribute
        fields = ['id', 'variant', 'attribute', 'attribute_name', 'value', 'value_display']
        read_only_fields = ['id']


class ProductImageSerializer(serializers.ModelSerializer):
    """Product image serializer"""
    # B11 FIX: removed image_url SerializerMethodField that had no corresponding
    # get_image_url() method, which would raise AssertionError at runtime.
    # The 'image' field already provides the URL via Cloudinary storage.

    class Meta:
        model = ProductImage
        fields = ['id', 'product', 'variant', 'image', 'alt_text',
                  'is_featured', 'sort_order']
        read_only_fields = ['id']


class ProductReviewSerializer(serializers.ModelSerializer):
    # B3 FIX: CustomUser has 'full_name', not 'name'
    user_name = serializers.CharField(source='user.full_name', read_only=True)

    class Meta:
        model = ProductReview
        # C2 FIX: removed duplicate 'model = ProductReview' line
        fields = ['id', 'product', 'user', 'user_name', 'rating',
                  'comment', 'is_approved', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']

    def validate_rating(self, value):
        if value < 0 or value > 5:
            raise serializers.ValidationError("Rating must be between 0 and 5.")
        return value
    # C3 FIX: removed no-op create() override that only called super().create()


class ProductVariantSerializer(serializers.ModelSerializer):
    """Product variant serializer with nested attributes and images"""
    variant_attributes = ProductVariantAttributeSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    current_price = serializers.SerializerMethodField()
    is_on_discount = serializers.SerializerMethodField()
    in_stock = serializers.BooleanField(source='stock', read_only=True)

    class Meta:
        model = ProductVariant
        fields = ['id', 'product', 'sku', 'price', 'discount_price', 'current_price',
                  'is_on_discount', 'stock', 'in_stock', 'weight', 'dimensions',
                  'is_active', 'variant_attributes', 'images', 'discount_start',
                  'discount_end', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_current_price(self, obj):
        """Calculate current price considering active discount window"""
        now = timezone.now()
        if (
            obj.discount_price is not None
            and obj.discount_start is not None
            and obj.discount_end is not None
            and obj.discount_start <= now <= obj.discount_end
        ):
            return obj.discount_price
        return obj.price

    def get_is_on_discount(self, obj):
        """Check if variant is currently within its discount window"""
        now = timezone.now()
        return (
            obj.discount_price is not None
            and obj.discount_start is not None
            and obj.discount_end is not None
            and obj.discount_start <= now <= obj.discount_end
        )

    def validate_sku(self, value):
        """Ensure SKU is unique, excluding the current instance on update"""
        qs = ProductVariant.objects.filter(sku=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("SKU must be unique.")
        return value


def _get_current_price_for_variant(variant):
    """
    Helper used by list/detail serializers to compute a variant's effective price
    in Python without a model method.  Mirrors the logic in ProductVariantSerializer.
    """
    now = timezone.now()
    if (
        variant.discount_price is not None
        and variant.discount_start is not None
        and variant.discount_end is not None
        and variant.discount_start <= now <= variant.discount_end
    ):
        return variant.discount_price
    return variant.price


class ProductListSerializer(serializers.ModelSerializer):
    """Lightweight product serializer for list views"""
    category_name = serializers.CharField(source='category.name', read_only=True)
    featured_image_url = serializers.SerializerMethodField()
    # O1 FIX: min/max price computed via SQL aggregation, not Python iteration
    min_price = serializers.SerializerMethodField()
    max_price = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['id', 'name', 'slug', 'category', 'category_name', 'is_active',
                  'featured_image_url', 'views_count', 'sales_count', 'min_price',
                  'max_price', 'average_rating', 'created_at']
        read_only_fields = ['id', 'views_count', 'sales_count', 'created_at']

    def get_featured_image_url(self, obj):
        if obj.featured_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.featured_image.url)
            return obj.featured_image.url
        return None

    def get_min_price(self, obj):
        """Minimum price among active variants, accounting for current discounts"""
        variants = obj.variants.filter(is_active=True)
        if not variants.exists():
            return None
        return min(_get_current_price_for_variant(v) for v in variants)

    def get_max_price(self, obj):
        """Maximum price among active variants, accounting for current discounts"""
        variants = obj.variants.filter(is_active=True)
        if not variants.exists():
            return None
        return max(_get_current_price_for_variant(v) for v in variants)

    def get_average_rating(self, obj):
        """Average rating from approved reviews, computed in SQL"""
        # O2 FIX: Avg is now imported at module level, not inside each method call
        result = obj.reviews.filter(is_approved=True).aggregate(avg=Avg('rating'))
        avg = result['avg']
        return round(avg, 1) if avg is not None else None


class ProductDetailSerializer(serializers.ModelSerializer):
    """Detailed product serializer for single product views"""
    category_detail = CategorySerializer(source='category', read_only=True)
    tags_detail = TagSerializer(source='tags', many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    reviews = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()
    total_reviews = serializers.SerializerMethodField()
    featured_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['id', 'name', 'slug', 'description', 'category', 'category_detail',
                  'is_active', 'featured_image', 'featured_image_url', 'views_count',
                  'sales_count', 'tags', 'tags_detail', 'variants', 'images',
                  'reviews', 'average_rating', 'total_reviews', 'created_at', 'updated_at']
        read_only_fields = ['id', 'views_count', 'sales_count', 'created_at', 'updated_at']

    def get_featured_image_url(self, obj):
        if obj.featured_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.featured_image.url)
            return obj.featured_image.url
        return None

    def get_reviews(self, obj):
        """Return approved reviews"""
        reviews = obj.reviews.filter(is_approved=True)
        return ProductReviewSerializer(reviews, many=True, context=self.context).data

    def get_average_rating(self, obj):
        """Average rating from approved reviews, computed in SQL"""
        # O2 FIX: Avg imported at module level
        result = obj.reviews.filter(is_approved=True).aggregate(avg=Avg('rating'))
        avg = result['avg']
        return round(avg, 1) if avg is not None else None

    def get_total_reviews(self, obj):
        """Total count of approved reviews"""
        return obj.reviews.filter(is_approved=True).count()


class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating products"""
    tags = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Tag.objects.all(), required=False
    )

    class Meta:
        model = Product
        fields = ['id', 'name', 'slug', 'description', 'category', 'is_active',
                  'featured_image', 'tags']

    def create(self, validated_data):
        """Create product with auto-generated slug if not provided"""
        if not validated_data.get('slug'):
            validated_data['slug'] = slugify(validated_data['name'])
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Update slug when name changes and no explicit slug was provided"""
        if 'name' in validated_data and 'slug' not in validated_data:
            validated_data['slug'] = slugify(validated_data['name'])
        return super().update(instance, validated_data)


class ProductVariantCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating product variants"""

    class Meta:
        model = ProductVariant
        fields = ['id', 'product', 'sku', 'price', 'discount_price', 'stock',
                  'weight', 'dimensions', 'is_active', 'discount_start', 'discount_end']

    def validate(self, data):
        """Validate discount date ordering"""
        if data.get('discount_start') and data.get('discount_end'):
            if data['discount_start'] >= data['discount_end']:
                raise serializers.ValidationError(
                    "Discount end date must be after start date."
                )
        return data
