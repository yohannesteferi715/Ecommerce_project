# B1 FIX: previous file imported non-existent 'CategoryListView' and registered
# only one broken route.  This file now imports the correct views and registers
# the full route set that matches the defined view classes.

from django.urls import path

from project_apps.products.api.views import (
    AttributeDetailAPIView,
    AttributeListCreateAPIView,
    AttributeValueDetailAPIView,
    AttributeValueListCreateAPIView,
    CategoryDetailAPIView,
    CategoryListCreateAPIView,
    ProductCreateAPIView,
    ProductDeleteAPIView,
    ProductDetailAPIView,
    ProductImageDetailAPIView,
    ProductImageListCreateAPIView,
    ProductListAPIView,
    ProductReviewDetailAPIView,
    ProductReviewListCreateAPIView,
    ProductUpdateAPIView,
    ProductVariantAttributeDetailAPIView,
    ProductVariantAttributeListCreateAPIView,
    ProductVariantDetailAPIView,
    ProductVariantListCreateAPIView,
    TagDetailAPIView,
    TagListCreateAPIView,
    AdminReviewApproveAPIView,
    AdminReviewListAPIView,
)

app_name = 'products'

urlpatterns = [
    # Category URLs
    path('categories/', CategoryListCreateAPIView.as_view(), name='category-list'),
    path('categories/<slug:slug>/', CategoryDetailAPIView.as_view(), name='category-detail'),

    # Tag URLs
    path('tags/', TagListCreateAPIView.as_view(), name='tag-list'),
    path('tags/<slug:slug>/', TagDetailAPIView.as_view(), name='tag-detail'),

    # Attribute URLs
    path('attributes/', AttributeListCreateAPIView.as_view(), name='attribute-list'),
    path('attributes/<int:pk>/', AttributeDetailAPIView.as_view(), name='attribute-detail'),

    # Attribute Value URLs
    path('attribute-values/', AttributeValueListCreateAPIView.as_view(), name='attribute-value-list'),
    path('attribute-values/<int:pk>/', AttributeValueDetailAPIView.as_view(), name='attribute-value-detail'),

    # Product URLs
    path('products/', ProductListAPIView.as_view(), name='product-list'),
    path('products/create/', ProductCreateAPIView.as_view(), name='product-create'),
    path('products/<slug:slug>/', ProductDetailAPIView.as_view(), name='product-detail'),
    path('products/<slug:slug>/update/', ProductUpdateAPIView.as_view(), name='product-update'),
    path('products/<slug:slug>/delete/', ProductDeleteAPIView.as_view(), name='product-delete'),

    # Product Variant URLs
    path('variants/', ProductVariantListCreateAPIView.as_view(), name='variant-list'),
    path('products/<int:product_id>/variants/', ProductVariantListCreateAPIView.as_view(), name='product-variant-list'),
    path('variants/<int:pk>/', ProductVariantDetailAPIView.as_view(), name='variant-detail'),

    # Product Variant Attribute URLs
    path('variant-attributes/', ProductVariantAttributeListCreateAPIView.as_view(), name='variant-attribute-list'),
    path('variant-attributes/<int:pk>/', ProductVariantAttributeDetailAPIView.as_view(), name='variant-attribute-detail'),

    # Product Image URLs
    path('product-images/', ProductImageListCreateAPIView.as_view(), name='product-image-list'),
    path('products/<int:product_id>/images/', ProductImageListCreateAPIView.as_view(), name='product-image-list-by-product'),
    path('variants/<int:variant_id>/images/', ProductImageListCreateAPIView.as_view(), name='product-image-list-by-variant'),
    path('product-images/<int:pk>/', ProductImageDetailAPIView.as_view(), name='product-image-detail'),

    # Product Review URLs
    path('products/<int:product_id>/reviews/', ProductReviewListCreateAPIView.as_view(), name='product-review-list'),
    path('reviews/<int:pk>/', ProductReviewDetailAPIView.as_view(), name='product-review-detail'),

    # Admin Review URLs
    path('admin/reviews/', AdminReviewListAPIView.as_view(), name='admin-review-list'),
    path('admin/reviews/<int:pk>/approve/', AdminReviewApproveAPIView.as_view(), name='admin-review-approve'),
]
