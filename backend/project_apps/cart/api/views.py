"""
Cart views
==========
Follows the same pattern as the products app: DRF generic views and APIView
for custom actions.  All views require authentication — anonymous requests
receive HTTP 401 before any cart logic runs.

Endpoint map
------------
GET    /api/cart/             CartRetrieveView       — retrieve or show empty cart
DELETE /api/cart/clear/       CartClearView          — clear all items
POST   /api/cart/items/       CartItemAddView        — add an item
PATCH  /api/cart/items/{id}/  CartItemDetailView     — set item quantity
DELETE /api/cart/items/{id}/  CartItemDetailView     — remove one item

Error handling
--------------
Service exceptions (ProductNotAvailable, InvalidQuantity, ItemNotFound) are
caught at the view level and converted to structured JSON responses with
appropriate HTTP status codes.  Internal exception details are never leaked.
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from project_apps.cart.serializers import (
    AddItemSerializer,
    CartSerializer,
    CartItemSerializer,
    SetQuantitySerializer,
)
from project_apps.cart.services import (
    CartError,
    InvalidQuantity,
    ItemNotFound,
    ProductNotAvailable,
    add_item,
    clear_cart,
    get_cart_or_none,
    remove_item,
    set_item_quantity,
)


# ---------------------------------------------------------------------------
# Cart-level views
# ---------------------------------------------------------------------------

class CartRetrieveView(APIView):
    """
    GET /api/cart/

    Returns the authenticated customer's active cart.
    If no cart exists yet, returns an empty-cart representation without
    creating a cart record (carts are created lazily on first item add).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cart = get_cart_or_none(request.user)
        if cart is None:
            # Return a consistent empty-cart shape rather than 404 so the
            # frontend always gets the same structure regardless of cart state.
            return Response(
                {
                    "id": None,
                    "status": "active",
                    "items": [],
                    "subtotal": "0.00",
                    "item_count": 0,
                    "total_units": 0,
                    "created_at": None,
                    "updated_at": None,
                },
                status=status.HTTP_200_OK,
            )
        serializer = CartSerializer(cart)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CartClearView(APIView):
    """
    DELETE /api/cart/clear/

    Removes all items from the authenticated customer's active cart.
    Returns 204 No Content whether or not the cart had items (idempotent).
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        clear_cart(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Cart item views
# ---------------------------------------------------------------------------

class CartItemAddView(APIView):
    """
    POST /api/cart/items/

    Adds a product variant to the cart.  If the variant is already present,
    the quantity is incremented.  Creates the cart record on first use.

    Request body:
        { "variant_id": <int>, "quantity": <int> }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AddItemSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        variant_id = serializer.validated_data["variant_id"]
        quantity = serializer.validated_data["quantity"]

        try:
            item = add_item(request.user, variant_id, quantity)
        except ProductNotAvailable as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except InvalidQuantity as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except CartError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            CartItemSerializer(item).data,
            status=status.HTTP_201_CREATED,
        )


class CartItemDetailView(APIView):
    """
    PATCH /api/cart/items/{id}/  — set quantity (replaces current value)
    DELETE /api/cart/items/{id}/ — remove item

    Both operations are scoped to the authenticated customer's active cart.
    Returns 404 if the item does not exist or belongs to another customer.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk: int):
        serializer = SetQuantitySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            item = set_item_quantity(
                request.user, pk, serializer.validated_data["quantity"]
            )
        except ItemNotFound as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except InvalidQuantity as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except CartError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(CartItemSerializer(item).data, status=status.HTTP_200_OK)

    def delete(self, request, pk: int):
        try:
            remove_item(request.user, pk)
        except ItemNotFound as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except CartError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_204_NO_CONTENT)
