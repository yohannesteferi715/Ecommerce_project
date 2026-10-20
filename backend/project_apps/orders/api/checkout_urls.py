from django.urls import path

from project_apps.orders.api.views import CheckoutView

app_name = "checkout"

urlpatterns = [
    path("", CheckoutView.as_view(), name="checkout"),
]
