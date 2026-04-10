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
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']


class TagDetailAPIView(RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a tag"""
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    lookup_url_kwarg = 'slug'







