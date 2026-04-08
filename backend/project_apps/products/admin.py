from django.contrib import admin
from .models import Category, Product, Attribute, AttributeValue, ProductVariant, ProductVariantAttribute, ProductImage, ProductReview, Tag

for model in [Category, Product, Attribute, AttributeValue, ProductVariant, ProductVariantAttribute, ProductImage, ProductReview, Tag]:
    admin.site.register(model)
