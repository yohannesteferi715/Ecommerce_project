from django.db.models import F, Min, Max, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from django_filters.rest_framework import  DjangoFilterBackend  # B2 FIX: was missing

from rest_framework import filters, status
from rest_framework.generics import (
    CreateAPIView,
    DestroyAPIView,
    ListAPIView,
    ListCreateAPIView,
    RetrieveAPIView,
    RetrieveUpdateDestroyAPIView,
    UpdateAPIView,
)
from rest_framework.permissions import IsAdminUser, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView

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
from project_apps.products.api.serializers import (
    AttributeSerializer,
    AttributeValueSerializer,
    CategorySerializer,
    ProductCreateUpdateSerializer,
    ProductDetailSerializer,
    ProductImageSerializer,
    ProductListSerializer,
    ProductReviewSerializer,
    ProductVariantAttributeSerializer,
    ProductVariantCreateUpdateSerializer,
    ProductVariantSerializer,
    TagSerializer,
)
from .permissions import IsAdminOrReadOnly, IsOwnerOrReadOnly


# ---------------------------------------------------------------------------
# Category Views
# ---------------------------------------------------------------------------

class CategoryListCreateAPIView(ListCreateAPIView):
    """List all top-level active categories or create a new category"""
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name']
    ordering_fields = ['name']
    ordering = ['name']

    def get_queryset(self):
        # Returns top-level active categories only
        return Category.objects.filter(is_active=True, parent=None)


class CategoryDetailAPIView(RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a category"""
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    lookup_url_kwarg = 'slug'


# ---------------------------------------------------------------------------
# Tag Views
# ---------------------------------------------------------------------------

class TagListCreateAPIView(ListCreateAPIView):
    """List all tags or create a new tag"""
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name']
    # C5 FIX: removed 'created_at' — Tag model has no created_at field
    ordering_fields = ['name']
    ordering = ['name']


class TagDetailAPIView(RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a tag"""
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [IsAdminUser]
    lookup_field = 'slug'
    lookup_url_kwarg = 'slug'


# ---------------------------------------------------------------------------
# Attribute Views
# ---------------------------------------------------------------------------

class AttributeListCreateAPIView(ListCreateAPIView):
    """List all attributes or create a new attribute"""
    queryset = Attribute.objects.all()
    serializer_class = AttributeSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']


class AttributeDetailAPIView(RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete an attribute"""
    queryset = Attribute.objects.all()
    serializer_class = AttributeSerializer
    permission_classes = [IsAdminUser]


# ---------------------------------------------------------------------------
# Attribute Value Views
# ---------------------------------------------------------------------------

class AttributeValueListCreateAPIView(ListCreateAPIView):
    """List attribute values or create a new attribute value"""
    queryset = AttributeValue.objects.all()
    serializer_class = AttributeValueSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['attribute']
    ordering_fields = ['value', 'sort_order']
    ordering = ['sort_order']


class AttributeValueDetailAPIView(RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete an attribute value"""
    queryset = AttributeValue.objects.all()
    serializer_class = AttributeValueSerializer
    permission_classes = [IsAdminOrReadOnly]


# ---------------------------------------------------------------------------
# Product Variant Attribute Views
# ---------------------------------------------------------------------------

class ProductVariantAttributeListCreateAPIView(ListCreateAPIView):
    """List variant attributes or create new"""
    queryset = ProductVariantAttribute.objects.all()
    serializer_class = ProductVariantAttributeSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['variant', 'attribute']


class ProductVariantAttributeDetailAPIView(RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a variant attribute"""
    queryset = ProductVariantAttribute.objects.all()
    serializer_class = ProductVariantAttributeSerializer
    permission_classes = [IsAdminUser]


# ---------------------------------------------------------------------------
# Product Image Views
# ---------------------------------------------------------------------------

class ProductImageListCreateAPIView(ListCreateAPIView):
    """List product images or upload new image"""
    serializer_class = ProductImageSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        product_id = self.kwargs.get('product_id')
        variant_id = self.kwargs.get('variant_id')
        queryset = ProductImage.objects.all()
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        if variant_id:
            queryset = queryset.filter(variant_id=variant_id)
        return queryset


class ProductImageDetailAPIView(RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a product image"""
    queryset = ProductImage.objects.all()
    serializer_class = ProductImageSerializer
    permission_classes = [IsAdminUser]


# ---------------------------------------------------------------------------
# Product Review Views
# ---------------------------------------------------------------------------

class ProductReviewListCreateAPIView(ListCreateAPIView):
    """List product reviews or create a new review"""
    serializer_class = ProductReviewSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['rating', 'is_approved']
    ordering_fields = ['rating', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        product_id = self.kwargs.get('product_id')
        # B12 FIX: always return a queryset; never implicitly return None
        if product_id:
            return ProductReview.objects.filter(
                product_id=product_id,
                is_approved=True,
            )
        return ProductReview.objects.filter(is_approved=True)

    def perform_create(self, serializer):
        product_id = self.kwargs.get('product_id')
        product = get_object_or_404(Product, id=product_id, is_active=True)
        serializer.save(user=self.request.user, product=product)


class ProductReviewDetailAPIView(RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a product review"""
    queryset = ProductReview.objects.all()
    serializer_class = ProductReviewSerializer
    permission_classes = [IsOwnerOrReadOnly]

    def perform_update(self, serializer):
        # Reset approval status when a review is edited
        serializer.save(is_approved=False)


# ---------------------------------------------------------------------------
# Admin Review Management Views
# ---------------------------------------------------------------------------

class AdminReviewListAPIView(ListAPIView):
    """List all reviews for admin with filtering"""
    serializer_class = ProductReviewSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['rating', 'is_approved', 'product']
    # B3 / model fix: corrected field name from user__name to user__full_name
    search_fields = ['comment', 'user__email', 'user__full_name']

    def get_queryset(self):
        return ProductReview.objects.select_related('user', 'product')


class AdminReviewApproveAPIView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        review = get_object_or_404(ProductReview, pk=pk)
        serializer = ProductReviewSerializer(review, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"message": "Review updated successfully", "review": serializer.data},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Product Variant Views
# ---------------------------------------------------------------------------

class ProductVariantListCreateAPIView(ListCreateAPIView):
    """List all variants or create a new variant"""
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        product_id = self.kwargs.get('product_id')
        if product_id:
            return ProductVariant.objects.filter(product_id=product_id)
        return ProductVariant.objects.all()

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ProductVariantCreateUpdateSerializer
        return ProductVariantSerializer

    def perform_create(self, serializer):
        serializer.save(product_id=self.kwargs['product_id'])


class ProductVariantDetailAPIView(RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a product variant"""
    queryset = ProductVariant.objects.all()
    # B10 FIX: missing permission_classes; any unauthenticated user could mutate variants
    permission_classes = [IsAdminOrReadOnly]
 
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return ProductVariantCreateUpdateSerializer
        return ProductVariantSerializer


# ---------------------------------------------------------------------------
# Product Views
# ---------------------------------------------------------------------------

class ProductListAPIView(ListAPIView):
    """List all active products with filtering, searching and ordering"""
    serializer_class = ProductListSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'is_active', 'tags']
    search_fields = ['name', 'description', 'category__name']
    ordering_fields = ['created_at', 'views_count', 'sales_count']
    ordering = ['-created_at']

    def get_queryset(self):
        queryset = Product.objects.filter(is_active=True)

        # O4 / B5 FIX: price-range filter using DB aggregation, not Python iteration
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        if min_price or max_price:
            # Annotate each product with its cheapest active variant price
            queryset = queryset.annotate(
                cheapest_variant=Min('variants__price', filter=Q(variants__is_active=True))
            )
            if min_price:
                queryset = queryset.filter(cheapest_variant__gte=float(min_price))
            if max_price:
                queryset = queryset.filter(cheapest_variant__lte=float(max_price))

        # Filter by attribute value
        attribute_search = self.request.query_params.get('attribute')
        if attribute_search:
            queryset = queryset.filter(
                variants__variant_attributes__value__value__icontains=attribute_search
            ).distinct()

        # On-sale products
        on_sale = self.request.query_params.get('on_sale')
        if on_sale and on_sale.lower() == 'true':
            now = timezone.now()
            queryset = queryset.filter(
                variants__discount_price__isnull=False,
                variants__discount_start__lte=now,
                variants__discount_end__gte=now,
            ).distinct()

        # In-stock products
        in_stock = self.request.query_params.get('in_stock')
        if in_stock and in_stock.lower() == 'true':
            queryset = queryset.filter(variants__stock__gt=0).distinct()

        return queryset

    # B6 FIX: removed the list() override that crashed when no paginator was
    # configured (self.paginator would be None, causing AttributeError).
    # The default ListAPIView.list() is correct and sufficient.


class ProductDetailAPIView(RetrieveAPIView):
    """Retrieve detailed product information"""
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductDetailSerializer
    lookup_field = 'slug'
    lookup_url_kwarg = 'slug'

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Increment view count atomically at DB level
        Product.objects.filter(pk=instance.pk).update(views_count=F('views_count') + 1)
        instance.refresh_from_db(fields=['views_count'])
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class ProductCreateAPIView(CreateAPIView):
    """Create a new product (Admin only)"""
    queryset = Product.objects.all()
    serializer_class = ProductCreateUpdateSerializer
    permission_classes = [IsAdminOrReadOnly]


class ProductUpdateAPIView(UpdateAPIView):
    """Update a product (Admin only)"""
    queryset = Product.objects.all()
    serializer_class = ProductCreateUpdateSerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    lookup_url_kwarg = 'slug'


class ProductDeleteAPIView(DestroyAPIView):
    """Delete a product (Admin only)"""
    queryset = Product.objects.all()
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    lookup_url_kwarg = 'slug'
