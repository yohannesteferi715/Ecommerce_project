from rest_framework.permissions import (IsAdminUser,IsAuthenticatedOrReadOnly)


from rest_framework.generics import (
    ListAPIView, RetrieveAPIView, CreateAPIView, 
    UpdateAPIView, DestroyAPIView, ListCreateAPIView,
    RetrieveUpdateAPIView, RetrieveUpdateDestroyAPIView
)

from  django.shortcuts import get_object_or_404

from project_apps.products.api.serializers import (
    CategorySerializer, TagSerializer, AttributeSerializer,
    AttributeValueSerializer, ProductListSerializer, 
    ProductDetailSerializer, ProductCreateUpdateSerializer,
    ProductVariantSerializer, ProductVariantCreateUpdateSerializer,
    ProductImageSerializer, ProductReviewSerializer,
    ProductVariantAttributeSerializer
)


from project_apps.products.models import (
    Product, Category, Attribute, AttributeValue,
    ProductVariant, ProductVariantAttribute,
    ProductImage, ProductReview, Tag
)
from .permissions import IsAdminOrReadOnly


from project_apps.products.models import Category


from project_apps.products.api.serializers import CategorySerializer


class CategoryListCreateAPIView(ListCreateAPIView):
    
        """List all categories or create a new category"""
        
        serializer_class = CategorySerializer
        permission_classes = [IsAdminOrReadOnly]
        filter_backends = [filters.SearchFilter, filters.OrderingFilter]
        search_fields = ['name']
        ordering_fields = ['name']
        ordering = ['name']
    
        def get_queryset(self):
            #returns toplevel  active categories 
            return Category.objects.filter(is_active=True,parent=None)


class CategoryDetailAPIView(RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a category"""
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    lookup_url_kwarg = 'slug'


# Tag Views
class TagListCreateAPIView(ListCreateAPIView):
    """List all tags or create a new tag"""
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']


class TagDetailAPIView(RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a tag"""
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [IsAdminUser]
    lookup_field = 'slug'
    lookup_url_kwarg = 'slug'

# Attribute Views
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



# Product Variant Attribute Views
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

# Product Image Views
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

# Product Review Views
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
        if product_id:
            return ProductReview.objects.filter(
                product_id=product_id, 
                is_approved=True
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
        # Reset approval status when review is updated
        serializer.save(is_approved=False)