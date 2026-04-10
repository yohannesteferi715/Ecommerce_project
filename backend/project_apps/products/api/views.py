from rest_framework.generics import (
    
    
    ListCreateAPIView
    
    
    
)


from project_apps.products.models import Category


from project_apps.products.api.serializers import CategorySerializer


class CategoryListCreateAPIView(ListCreateAPIView):
    
        """List all categories or create a new category"""
        
        serializer_class = CategorySerializer
        permission_classes = [IsAdminOrReadOnly]
        filter_backends = [filters.SearchFilter, filters.OrderingFilter]
        search_fields = ['name']
        ordering_fields = ['name', 'created_at']
        ordering = ['name']
    
        def get_queryset(self):
            #returns toplevel  active categories 
            return Category.objects.filter(is_active=True,parent=None)



####views for products ############













