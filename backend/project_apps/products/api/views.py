from rest_framework import generics
from products.models import  Category
from products.api.serializers import CategorySerializer


class CategoryListView(generics.ListAPIView):
    
    serializer_class=CategorySerializer
    
    def get_queryset(self):
        #returns toplevel  active categories 
       return Category.objects.filter(is_active=True,parent=None)












