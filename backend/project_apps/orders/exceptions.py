"""
Domain exceptions for the orders app.

Views catch these and map them to HTTP responses. Unexpected errors
are left uncaught so Django/DRF can log them.
"""


class OrderError(Exception):
    """Base class for orders-domain errors."""


class EmptyCart(OrderError):
    """The cart has no items."""


class CartNotEligible(OrderError):
    """The cart is missing, inactive, already checked out, or not owned."""


class InvalidQuantity(OrderError):
    """A cart line has a quantity that cannot be purchased."""


class ProductUnavailable(OrderError):
    """A variant or its product is inactive, missing, or not purchasable."""


class InsufficientStock(OrderError):
    """Requested quantity exceeds locked, current stock."""


class InvalidAddress(OrderError):
    """Shipping address is incomplete or invalid."""


class IdempotencyConflict(OrderError):
    """The same idempotency key was reused with different checkout parameters."""


class CheckoutInProgress(OrderError):
    """Another request is currently completing this idempotency key."""


class InvalidTransition(OrderError):
    """The requested status change is not allowed from the current state."""


class OrderNotCancellable(OrderError):
    """The order cannot be cancelled in its current state."""


class OrderAlreadyCancelled(OrderError):
    """The order is already cancelled."""


class OrderNotFound(OrderError):
    """The order does not exist or is not visible to the caller."""


class OrderPricingError(OrderError):
    """A calculated monetary amount is invalid."""


class PaymentResultError(OrderError):
    """A trusted payment-result update could not be applied."""
