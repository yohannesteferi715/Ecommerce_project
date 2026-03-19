from rest_framework import generics

from products.api.serializers import CategorySerializer


class CategoryListView(generics.ListAPIView):
    
    serializer_class=CategorySerializer
    
    def get_queryset(self):
        return super().get_queryset()













