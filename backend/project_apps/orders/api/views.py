"""
Customer-facing order views.

POST /api/checkout/              create order from cart
GET  /api/orders/                list current user's orders
GET  /api/orders/<uuid>/         retrieve one order
POST /api/orders/<uuid>/cancel/  cancel an eligible order
"""

from django.db.models import Count
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from project_apps.orders.api.serializers import (
    CancelOrderSerializer,
    CheckoutRequestSerializer,
    OrderDetailSerializer,
    OrderListSerializer,
)
from project_apps.orders.exceptions import (
    CartNotEligible,
    CheckoutInProgress,
    EmptyCart,
    IdempotencyConflict,
    InsufficientStock,
    InvalidAddress,
    InvalidQuantity,
    InvalidTransition,
    OrderAlreadyCancelled,
    OrderError,
    OrderNotCancellable,
    OrderNotFound,
    OrderPricingError,
    ProductUnavailable,
)
from project_apps.orders.models import Order
from project_apps.orders.services import cancel_order, checkout_cart


def _error(exc: Exception, http_status: int) -> Response:
    return Response({"detail": str(exc)}, status=http_status)


class CheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        payload = request.data
        if hasattr(payload, "copy"):
            payload = payload.copy()
        else:
            payload = dict(payload)
        if not payload.get("idempotency_key"):
            header_key = request.headers.get("Idempotency-Key")
            if header_key:
                payload["idempotency_key"] = header_key

        serializer = CheckoutRequestSerializer(data=payload)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        try:
            order = checkout_cart(
                user=request.user,
                shipping_address=data["shipping_address"],
                idempotency_key=data["idempotency_key"],
                cart_id=data.get("cart_id"),
            )
        except (EmptyCart, InvalidAddress, InvalidQuantity, ProductUnavailable, OrderPricingError) as exc:
            return _error(exc, status.HTTP_400_BAD_REQUEST)
        except InsufficientStock as exc:
            return _error(exc, status.HTTP_409_CONFLICT)
        except CartNotEligible as exc:
            return _error(exc, status.HTTP_404_NOT_FOUND)
        except (IdempotencyConflict, CheckoutInProgress) as exc:
            return _error(exc, status.HTTP_409_CONFLICT)
        except OrderError as exc:
            return _error(exc, status.HTTP_400_BAD_REQUEST)

        return Response(
            OrderDetailSerializer(order).data,
            status=status.HTTP_201_CREATED,
        )


class OrderListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        orders = (
            Order.objects.filter(user=request.user)
            .annotate(item_count=Count("items"))
            .order_by("-created_at")
        )
        return Response(
            OrderListSerializer(orders, many=True).data,
            status=status.HTTP_200_OK,
        )


class OrderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            order = (
                Order.objects.select_related("user")
                .prefetch_related("items")
                .get(pk=pk, user=request.user)
            )
        except (Order.DoesNotExist, ValueError):
            return Response(
                {"detail": "Order not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(OrderDetailSerializer(order).data, status=status.HTTP_200_OK)


class OrderCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        serializer = CancelOrderSerializer(data=request.data or {})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            order = cancel_order(
                order_id=pk,
                user=request.user,
                reason=serializer.validated_data.get("reason", ""),
            )
        except OrderNotFound as exc:
            return _error(exc, status.HTTP_404_NOT_FOUND)
        except OrderAlreadyCancelled as exc:
            return _error(exc, status.HTTP_409_CONFLICT)
        except (OrderNotCancellable, InvalidTransition) as exc:
            return _error(exc, status.HTTP_409_CONFLICT)
        except OrderError as exc:
            return _error(exc, status.HTTP_400_BAD_REQUEST)

        return Response(OrderDetailSerializer(order).data, status=status.HTTP_200_OK)
