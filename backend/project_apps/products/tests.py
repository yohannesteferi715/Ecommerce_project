

from rest_framework import serializers
from django.contrib.auth.models import User
from django.utils.text import slugify
from .models import (
    Product, Category, Attribute, AttributeValue, 
    ProductVariant, ProductVariantAttribute, 
    ProductImage, ProductReview,Tag
)


class CategorySerializer(serializers.ModelSerializer):
    """Category serializer with nested products count"""
    products_count = serializers.IntegerField(source='products.count', read_only=True)
    
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'description', 'parent', 'is_active', 
                  'created_at', 'updated_at', 'products_count']
        read_only_fields = ['id', 'created_at', 'updated_at']


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name', 'slug']
        read_only_fields = ['id']


class AttributeValueSerializer(serializers.ModelSerializer):
    """Attribute value serializer"""
    attribute_name = serializers.CharField(source='attribute.name', read_only=True)
    
    class Meta:
        model = AttributeValue
        fields = ['id', 'attribute', 'attribute_name', 'value', 'is_default', 
                  'sort_order', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class AttributeSerializer(serializers.ModelSerializer):
    







class ProductReviewSerializer(serializers.ModelSerializer):
    """Product review serializer"""
    user_name = serializers.CharField(source='user.username', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    
    class Meta:
        
    
    def validate_rating(self, value):
        """Validate rating is between 0 and 5"""
        if value < 0 or value > 5:
            raise serializers.ValidationError("Rating must be between 0 and 5")
        return value
    
    def create(self, validated_data):
        """Set the user to the current user"""
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)










class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating products"""
    tags = serializers.PrimaryKeyRelatedField(many=True, queryset=Tag.objects.all(), required=False)
    
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
        """Update product with slug update if name changes"""
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
        """Validate discount dates"""
        if data.get('discount_start') and data.get('discount_end'):
            if data['discount_start'] >= data['discount_end']:
                raise serializers.ValidationError(
                    "Discount end date must be after start date"
                )
        return data
    
    
    
    
    
    

