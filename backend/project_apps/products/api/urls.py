from django.urls import path

from project_apps.products.api.views import CategoryListView

urlpatterns = [
    path('categories',CategoryListView.as_view())
]
