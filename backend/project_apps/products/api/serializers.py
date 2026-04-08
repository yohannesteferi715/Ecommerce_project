from rest_framework import serializers
from django import models 
from django.utils.text import slugify

from products.models  import (
    Product, Category, Attribute, AttributeValue, 
    ProductVariant, ProductVariantAttribute, 
    ProductImage, ProductReview,Tag
)

class CategorySerializer(serializers.ModelSerializer):
    products_count = serializers.IntegerField(source='products.count', read_only=True)
    slug=serializers.ReadOnlyField()
    

    children=serializers.SerializerMethodField()
    
    class Meta :
        model=Category
        
        fields='__all__'
        
        
    def create(self, validated_data):
        validated_data['slug']=slugify(validated_data['name'])
        
        return super().create(validated_data)
    
        
   
    def update(self, instance, validated_data):
        
        if 'name' in validated_data and validated_data['name']!=instance.name:
            
            instance.slug=slugify(validated_data['name'])
            
        return super().update(instance, validated_data)
        
        
        
    def get_children(self,obj):
        
        if obj.children.exists():
            
            return CategorySerializer(obj.children.all(),many=True).data
        
        return []
        
        
### products serilaizers 



class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model=Tag
        fields = ['id', 'name', 'slug']
        read_only_fields = ['id']
        
        
        
class AttributeValueSerializer(serializers.ModelSerializer):
    
    attribute_name=serializers.CharField(source='attribute.name', read_only=True)
    
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
    image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = ProductImage
        fields = ['id', 'product', 'variant', 'image', 'image_url', 'alt_text', 
                  'is_featured', 'sort_order']
        read_only_fields = ['id']
    
    
class ProductReviewSerializer(serializers.ModelSerializer):
    
    user_name=serializers.CharField(source='user.name',read_only=True)
    
    class Meta:
        model= ProductReview
        model = ProductReview
        fields = ['id', 'product', 'user', 'user_name', 'rating', 
                  'comment', 'is_approved', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']
        
        
    def validate_rating(self, value):
        
        if value <0 or value > 5 :
            
            raise   serializers.ValidationError("rating must be btwn 0 and 5 ")
        
        return  value
    
      
    def create(self, validated_data):
        
        validated_data['user']=self.context['request'].user
        
        return super().create(validated_data)
        
        
        
        

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
        """Calculate current price considering discount"""
        from django.utils import timezone
        now = timezone.now()
        
        if (obj.discount_price and obj.discount_start and obj.discount_end and 
            obj.discount_start <= now <= obj.discount_end):
            return obj.discount_price
        return obj.price
    
    
    def get_is_on_discount(self, obj):
        """Check if product is currently on discount"""
        from django.utils import timezone
        now = timezone.now()
        
        return (obj.discount_price is not None and 
                obj.discount_start is not None and 
                obj.discount_end is not None and 
                obj.discount_start <= now <= obj.discount_end)
    
    def validate_sku(self, value):
        """Ensure SKU is unique"""
        if ProductVariant.objects.filter(sku=value).exists():
            if self.instance and self.instance.sku == value:
                return value
            raise serializers.ValidationError("SKU must be unique")
        return value
    
    
    
class ProductListSerializer(serializers.ModelSerializer):
    """Lightweight product serializer for list views"""
    category_name = serializers.CharField(source='category.name', read_only=True)
    featured_image_url = serializers.SerializerMethodField()
    min_price = serializers.SerializerMethodField()
    max_price = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = ['id', 'name', 'slug', 'category', 'category_name', 'is_active',
                  'featured_image_url', 'views_count', 'sales_count', 'min_price',
                  'max_price', 'average_rating', 'created_at']
        read_only_fields = ['id', 'views_count', 'sales_count', 'created_at']
    
    def get_min_price(self, obj):
        """Get minimum price among variants"""
        variants = obj.variants.filter(is_active=True)
        if variants.exists():
            prices = [v.get_current_price() if hasattr(v, 'get_current_price') 
                     else v.price for v in variants]
            return min(prices)
        return None
    
    def get_max_price(self, obj):
        """Get maximum price among variants"""
        variants = obj.variants.filter(is_active=True)
        if variants.exists():
            prices = [v.get_current_price() if hasattr(v, 'get_current_price') 
                     else v.price for v in variants]
            return max(prices)
        return None
    
    def get_average_rating(self, obj):
        """Calculate average rating from approved reviews"""
        approved_reviews = obj.reviews.filter(is_approved=True)
        if approved_reviews.exists():
            return round(approved_reviews.aggregate(models.Avg('rating'))['rating__avg'], 1)
        return None
    
    
    
    
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
    
    
    def get_reviews(self, obj):
        """Get approved reviews"""
        reviews = obj.reviews.filter(is_approved=True)
        return ProductReviewSerializer(reviews, many=True, context=self.context).data
    
    def get_average_rating(self, obj):
        """Calculate average rating from approved reviews"""
        approved_reviews = obj.reviews.filter(is_approved=True)
        if approved_reviews.exists():
            from django.db import models
            return round(approved_reviews.aggregate(models.Avg('rating'))['rating__avg'], 1)
        return None
    
    def get_total_reviews(self, obj):
        """Get total number of approved reviews"""
        return obj.reviews.filter(is_approved=True).count()
    
    
    
    
    
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