from django.urls import path

from project_apps.orders.api.views import OrderCancelView, OrderDetailView, OrderListView

app_name = "orders"

urlpatterns = [
    path("", OrderListView.as_view(), name="order-list"),
    path("<uuid:pk>/", OrderDetailView.as_view(), name="order-detail"),
    path("<uuid:pk>/cancel/", OrderCancelView.as_view(), name="order-cancel"),
]
