from rest_framework import serializers

from django.utils.text import slugify


from project_apps.products.models import Category

class CategorySerializer(serializers.ModelSerializer):
    slug=serializers.ReadOnlyField()
    
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
        
        
        
        