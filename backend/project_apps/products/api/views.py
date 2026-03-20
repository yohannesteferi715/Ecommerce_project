from rest_framework import generics
from project_apps.products.models import Category
from project_apps.products.api.serializers import CategorySerializer


class CategoryListView(generics.ListAPIView):
    
    serializer_class=CategorySerializer
    
    def get_queryset(self):
        #returns toplevel  active categories 
       return Category.objects.filter(is_active=True,parent=None)












