from rest_framework.views import APIView

from rest_framework.response import Response
from rest_framework import status, filters
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from django.db.models import Q, Avg, Count, F
from django.utils import timezone



from .permissions import IsAdminOrReadOnly, IsOwnerOrReadOnly

# Category Views
class CategoryListCreateAPIView(ListCreateAPIView):
   
    
    def get_queryset(self):
        queryset = super().get_queryset()
        # Filter by parent category
        parent_id = self.request.query_params.get('parent_id')
        if parent_id:
            queryset = queryset.filter(parent_id=parent_id)
        # Get only top-level categories
        is_top = self.request.query_params.get('is_top')
        if is_top and is_top.lower() == 'true':
            queryset = queryset.filter(parent__isnull=True)
        return queryset

class CategoryDetailAPIView(RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a category"""
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    lookup_url_kwarg = 'slug'






# Attribute Value Views
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

# Product Views
class ProductListAPIView(ListAPIView):
    """List all products with filtering, searching and ordering"""
    serializer_class = ProductListSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'is_active', 'tags']
    search_fields = ['name', 'description', 'category__name']
    ordering_fields = ['price', 'created_at', 'views_count', 'sales_count', 'average_rating']
    ordering = ['-created_at']
    
    def get_queryset(self):
        queryset = Product.objects.filter(is_active=True)
        
        # Price range filtering
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        if min_price or max_price:
            products_with_price = []
            for product in queryset:
                min_product_price = product.get_min_price() if hasattr(product, 'get_min_price') else None
                if min_product_price:
                    if min_price and min_product_price < float(min_price):
                        continue
                    if max_price and min_product_price > float(max_price):
                        continue
                    products_with_price.append(product.id)
            queryset = queryset.filter(id__in=products_with_price)
        
        # Search in attributes
        attribute_search = self.request.query_params.get('attribute')
        if attribute_search:
            queryset = queryset.filter(
                variants__variant_attributes__value__value__icontains=attribute_search
            ).distinct()
        
        # On sale products
        on_sale = self.request.query_params.get('on_sale')
        if on_sale and on_sale.lower() == 'true':
            now = timezone.now()
            queryset = queryset.filter(
                variants__discount_price__isnull=False,
                variants__discount_start__lte=now,
                variants__discount_end__gte=now
            ).distinct()
        
        # In stock products
        in_stock = self.request.query_params.get('in_stock')
        if in_stock and in_stock.lower() == 'true':
            queryset = queryset.filter(variants__stock__gt=0).distinct()
        
        return queryset
    
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        # Add pagination info
        response.data = {
            'count': self.paginator.page.paginator.count if self.paginator else len(response.data),
            'results': response.data
        }
        return response

class ProductDetailAPIView(RetrieveAPIView):
    """Retrieve detailed product information"""
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductDetailSerializer
    lookup_field = 'slug'
    lookup_url_kwarg = 'slug'
    
    def retrieve(self, request, *args, **kwargs):
        # Increment view count
        instance = self.get_object()
        instance.views_count = F('views_count') + 1
        instance.save(update_fields=['views_count'])
        instance.refresh_from_db()
        
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

# Product Variant Views
class ProductVariantListCreateAPIView(ListCreateAPIView):
    """List all variants or create a new variant"""
    serializer_class = ProductVariantSerializer
    
    def get_queryset(self):
        product_id = self.kwargs.get('product_id')
        if product_id:
            return ProductVariant.objects.filter(product_id=product_id)
        return ProductVariant.objects.all()
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ProductVariantCreateUpdateSerializer
        return ProductVariantSerializer

class ProductVariantDetailAPIView(RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a product variant"""
    queryset = ProductVariant.objects.all()
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return ProductVariantCreateUpdateSerializer
        return ProductVariantSerializer



# Product Image Views
class ProductImageListCreateAPIView(ListCreateAPIView):
    """List product images or upload new image"""
    serializer_class = ProductImageSerializer
    permission_classes = [IsAdminOrReadOnly]
    
    def get_queryset(self):
        product_id = self.kwargs.get('product_id')
        variant_id = self.kwargs.get('variant_id')
        if product_id:
            return ProductImage.objects.filter(product_id=product_id)
        elif variant_id:
            return ProductImage.objects.filter(variant_id=variant_id)
        return ProductImage.objects.all()


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

# Admin Review Management Views
class AdminReviewListAPIView(ListAPIView):
    """List all reviews for admin with filtering"""
    serializer_class = ProductReviewSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['rating', 'is_approved', 'product']
    search_fields = ['comment', 'user__email', 'user__name']
    
    def get_queryset(self):
        return ProductReview.objects.all()

class AdminReviewApproveAPIView(APIView):
    """Approve a review (Admin only)"""
    permission_classes = [IsAdminOrReadOnly]
    
    def post(self, request, pk):
        review = get_object_or_404(ProductReview, pk=pk)
        review.is_approved = True
        review.save()
        return Response({
            'message': 'Review approved successfully',
            'review': ProductReviewSerializer(review).data
        }, status=status.HTTP_200_OK)

# Search View
class ProductSearchAPIView(ListAPIView):
    """Advanced product search"""
    serializer_class = ProductListSerializer
    
    def get_queryset(self):
        queryset = Product.objects.filter(is_active=True)
        search_term = self.request.query_params.get('q', '')
        
        if search_term:
            queryset = queryset.filter(
                Q(name__icontains=search_term) |
                Q(description__icontains=search_term) |
                Q(category__name__icontains=search_term) |
                Q(tags__name__icontains=search_term) |
                Q(variants__sku__icontains=search_term)
            ).distinct()
        
        # Annotate with relevance score
        queryset = queryset.annotate(
            review_count=Count('reviews', filter=Q(reviews__is_approved=True)),
            search_relevance=Count('id')  # You can implement more complex relevance scoring
        ).order_by('-search_relevance', '-created_at')
        
        return queryset

# Related Products View
class RelatedProductsAPIView(APIView):
    """Get related products based on category and tags"""
    
    def get(self, request, slug):
        product = get_object_or_404(Product, slug=slug, is_active=True)
        
        # Get products from same category and tags
        related = Product.objects.filter(
            is_active=True
        ).exclude(
            id=product.id
        ).filter(
            Q(category=product.category) |
            Q(tags__in=product.tags.all())
        ).distinct().annotate(
            common_tags=Count('tags', filter=Q(tags__in=product.tags.all()))
        ).order_by('-common_tags', '-created_at')[:10]
        
        serializer = ProductListSerializer(related, many=True)
        return Response(serializer.data)

# Stats View
class ProductStatsAPIView(APIView):
    """Get product statistics"""
    permission_classes = [IsAdminOrReadOnly]
    
    def get(self, request):
        total_products = Product.objects.count()
        active_products = Product.objects.filter(is_active=True).count()
        total_categories = Category.objects.count()
        total_reviews = ProductReview.objects.filter(is_approved=True).count()
        
        # Top selling products
        top_selling = Product.objects.filter(
            is_active=True
        ).order_by('-sales_count')[:10]
        
        # Most viewed products
        most_viewed = Product.objects.filter(
            is_active=True
        ).order_by('-views_count')[:10]
        
        # Recent products
        recent_products = Product.objects.filter(
            is_active=True
        ).order_by('-created_at')[:10]
        
        stats = {
            'total_products': total_products,
            'active_products': active_products,
            'total_categories': total_categories,
            'total_reviews': total_reviews,
            'top_selling': ProductListSerializer(top_selling, many=True).data,
            'most_viewed': ProductListSerializer(most_viewed, many=True).data,
            'recent_products': ProductListSerializer(recent_products, many=True).data
        }
        
        return Response(stats)
    
    
    
    
    
    
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'products'

# If using ViewSets (optional alternative)
# router = DefaultRouter()
# router.register('categories', views.CategoryViewSet)
# router.register('products', views.ProductViewSet)

urlpatterns = [
    # Category URLs
    path('categories/', views.CategoryListCreateAPIView.as_view(), name='category-list'),
    path('categories/<slug:slug>/', views.CategoryDetailAPIView.as_view(), name='category-detail'),
    
    # Tag URLs
    path('tags/', views.TagListCreateAPIView.as_view(), name='tag-list'),
    path('tags/<slug:slug>/', views.TagDetailAPIView.as_view(), name='tag-detail'),
    
    # Attribute URLs
    path('attributes/', views.AttributeListCreateAPIView.as_view(), name='attribute-list'),
    path('attributes/<int:pk>/', views.AttributeDetailAPIView.as_view(), name='attribute-detail'),
    
    # Attribute Value URLs
    path('attribute-values/', views.AttributeValueListCreateAPIView.as_view(), name='attribute-value-list'),
    path('attribute-values/<int:pk>/', views.AttributeValueDetailAPIView.as_view(), name='attribute-value-detail'),
    
    # Product URLs
    path('products/', views.ProductListAPIView.as_view(), name='product-list'),
    path('products/search/', views.ProductSearchAPIView.as_view(), name='product-search'),
    path('products/stats/', views.ProductStatsAPIView.as_view(), name='product-stats'),
    path('products/create/', views.ProductCreateAPIView.as_view(), name='product-create'),
    path('products/<slug:slug>/', views.ProductDetailAPIView.as_view(), name='product-detail'),
    path('products/<slug:slug>/update/', views.ProductUpdateAPIView.as_view(), name='product-update'),
    path('products/<slug:slug>/delete/', views.ProductDeleteAPIView.as_view(), name='product-delete'),
    path('products/<slug:slug>/related/', views.RelatedProductsAPIView.as_view(), name='product-related'),
    
    # Product Variant URLs
    path('variants/', views.ProductVariantListCreateAPIView.as_view(), name='variant-list'),
    path('products/<int:product_id>/variants/', views.ProductVariantListCreateAPIView.as_view(), name='product-variant-list'),
    path('variants/<int:pk>/', views.ProductVariantDetailAPIView.as_view(), name='variant-detail'),
    
    # Product Variant Attribute URLs
    path('variant-attributes/', views.ProductVariantAttributeListCreateAPIView.as_view(), name='variant-attribute-list'),
    path('variant-attributes/<int:pk>/', views.ProductVariantAttributeDetailAPIView.as_view(), name='variant-attribute-detail'),
    
    # Product Image URLs
    path('product-images/', views.ProductImageListCreateAPIView.as_view(), name='product-image-list'),
    path('products/<int:product_id>/images/', views.ProductImageListCreateAPIView.as_view(), name='product-image-list-by-product'),
    path('variants/<int:variant_id>/images/', views.ProductImageListCreateAPIView.as_view(), name='product-image-list-by-variant'),
    path('product-images/<int:pk>/', views.ProductImageDetailAPIView.as_view(), name='product-image-detail'),
    
    # Product Review URLs
    path('products/<int:product_id>/reviews/', views.ProductReviewListCreateAPIView.as_view(), name='product-review-list'),
    path('reviews/<int:pk>/', views.ProductReviewDetailAPIView.as_view(), name='product-review-detail'),
    
    # Admin Review URLs
    path('admin/reviews/', views.AdminReviewListAPIView.as_view(), name='admin-review-list'),
    path('admin/reviews/<int:pk>/approve/', views.AdminReviewApproveAPIView.as_view(), name='admin-review-approve'),
]