from rest_framework.permissions import IsAdminUser


from rest_framework.generics import (
    ListAPIView, RetrieveAPIView, CreateAPIView, 
    UpdateAPIView, DestroyAPIView, ListCreateAPIView,
    RetrieveUpdateAPIView, RetrieveUpdateDestroyAPIView
)


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

