from rest_framework.generics import (
    RetrieveDestroyAPIView,
    
    ListCreateAPIView,
    
    
    
)

from .permissions import IsAdminOrReadOnly


from project_apps.products.models import Category


from project_apps.products.api.serializers import CategorySerializer


class CategoryListCreateAPIView(ListCreateAPIView):
    
        """List all categories or create a new category"""
        
        serializer_class = CategorySerializer
        permission_classes = [IsAdminOrReadOnly]
        filter_backends = [filters.SearchFilter, filters.OrderingFilter]
        search_fields = ['name']
        ordering_fields = ['name']
        ordering = ['name']
    
        def get_queryset(self):
            #returns toplevel  active categories 
            return Category.objects.filter(is_active=True,parent=None)


#Product related endpoints


class CategoryDetailAPIView(RetrieveDestroyAPIView):
    """Retrieve, update or delete a category"""
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'
    lookup_url_kwarg = 'slug'










