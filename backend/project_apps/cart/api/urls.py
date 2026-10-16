"""
Cart URL configuration
======================
All routes are prefixed with /api/cart/ in the root urls.py.

Route summary
-------------
GET    /api/cart/             retrieve cart (or empty-cart shape)
DELETE /api/cart/clear/       clear all items
POST   /api/cart/items/       add item
PATCH  /api/cart/items/{id}/  set item quantity
DELETE /api/cart/items/{id}/  remove item
"""

from django.urls import path

from project_apps.cart.api.views import (
    CartClearView,
    CartItemAddView,
    CartItemDetailView,
    CartRetrieveView,
)

app_name = "cart"

urlpatterns = [
    # Cart-level operations
    path("", CartRetrieveView.as_view(), name="cart-retrieve"),
    path("clear/", CartClearView.as_view(), name="cart-clear"),

    # Cart item operations
    path("items/", CartItemAddView.as_view(), name="cart-item-add"),
    path("items/<int:pk>/", CartItemDetailView.as_view(), name="cart-item-detail"),
]
