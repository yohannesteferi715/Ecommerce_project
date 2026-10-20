"""
Authoritative order pricing.

Cart totals are provisional. Checkout recalculates every amount here
and never trusts client-submitted prices, discounts, or totals.

Policy (no existing catalog-wide tax/shipping/promo engine):
  - Unit price is the variant's current effective price, including an
    active discount window. A price change between add-to-cart and
    checkout is applied at checkout (server-authoritative).
  - Line total = unit_price * quantity, quantized.
  - Shipping fee and tax default to 0.00 — no rates exist in the project.
  - Order-level discount_amount is 0.00. Variant discounts are already
    reflected in unit_price and must not be subtracted again.
  - Payable total cannot be negative.

Precision: ProductVariant.price uses decimal_places=2. All amounts are
quantized with ROUND_HALF_UP to two fractional digits. The stored
currency code is informational; this project does not yet convert
between currencies or vary scale per ISO 4217 currency.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

MONEY_QUANT = Decimal("0.01")
ZERO = Decimal("0.00")


def quantize_money(amount: Decimal) -> Decimal:
    """Round a Decimal to the project's monetary scale."""
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    return amount.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def get_effective_unit_price(variant, *, now=None) -> Decimal:
    """
    Return the current sell price for *variant*.

    Mirrors CartItem.unit_price and ProductVariantSerializer.get_current_price:
    discount_price applies only when discount_start/end bound the current time.
    """
    now = now or timezone.now()
    if (
        variant.discount_price is not None
        and variant.discount_start is not None
        and variant.discount_end is not None
        and variant.discount_start <= now <= variant.discount_end
    ):
        return quantize_money(variant.discount_price)
    return quantize_money(variant.price)


def calculate_line_total(unit_price: Decimal, quantity: int) -> Decimal:
    if quantity < 1:
        raise ValueError("quantity must be >= 1")
    return quantize_money(quantize_money(unit_price) * quantity)


@dataclass(frozen=True)
class OrderTotals:
    subtotal: Decimal
    shipping_fee: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    total: Decimal


def calculate_order_totals(
    line_totals: list[Decimal],
    *,
    shipping_fee: Decimal = ZERO,
    tax_amount: Decimal = ZERO,
    discount_amount: Decimal = ZERO,
) -> OrderTotals:
    """
    total = subtotal + shipping_fee + tax_amount - discount_amount

    Raises ValueError if any component is negative or total would be negative.
    """
    shipping_fee = quantize_money(shipping_fee)
    tax_amount = quantize_money(tax_amount)
    discount_amount = quantize_money(discount_amount)

    if shipping_fee < ZERO or tax_amount < ZERO or discount_amount < ZERO:
        raise ValueError("Monetary components must be nonnegative.")

    subtotal = ZERO
    for line in line_totals:
        line = quantize_money(line)
        if line < ZERO:
            raise ValueError("Line totals must be nonnegative.")
        subtotal += line
    subtotal = quantize_money(subtotal)

    total = quantize_money(subtotal + shipping_fee + tax_amount - discount_amount)
    if total < ZERO:
        raise ValueError("Payable total cannot be negative.")

    return OrderTotals(
        subtotal=subtotal,
        shipping_fee=shipping_fee,
        tax_amount=tax_amount,
        discount_amount=discount_amount,
        total=total,
    )
