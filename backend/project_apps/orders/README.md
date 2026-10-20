# Orders

Customer checkout, historical order records, cancellation, and inventory
deduction. Payments are **not** implemented here.

## Models

### Order

| Field | Role |
| --- | --- |
| `id` | UUID primary key |
| `order_number` | Public unique identifier (`ORD-YYYYMMDD-XXXXXXXX`) |
| `user` | `PROTECT` — deleting a user does not delete orders |
| `cart` | Source cart (`SET_NULL`) |
| `status` | Order lifecycle |
| `payment_status` | Payment summary only (not a ledger) |
| `fulfillment_status` | Shipping lifecycle |
| `subtotal`, `shipping_fee`, `discount_amount`, `tax_amount`, `total` | Server-calculated `Decimal` amounts |
| `currency` | ISO code from `settings.DEFAULT_CURRENCY` (default `USD`) |
| `shipping_address` | Immutable JSON snapshot |
| `inventory_restored` | Guards against double stock restore |

Database checks enforce nonnegative money and
`total = subtotal + shipping_fee + tax_amount - discount_amount`.

### OrderItem

One row per variant (same uniqueness as cart lines). Snapshots:

- product name, SKU, variant attributes
- unit price actually charged
- quantity (`>= 1`)
- line total (`unit_price * quantity`)

`variant` uses `SET_NULL` so catalog deletion does not erase purchase history.

### CheckoutIdempotencyRecord

Unique on `(user, key)`. Created in the **same transaction** as the order.

## Lifecycle

Order status, payment status, and fulfillment status are independent.

**Order status**

```
pending → confirmed → processing → completed
pending → cancelled
confirmed → cancelled
```

`processing → cancelled` is not allowed. Completed and cancelled are terminal.

**Payment status:** `unpaid`, `pending`, `paid`, `failed`, `refunded`.

Checkout always creates `status=pending` and `payment_status=unpaid`.
Checkout never marks an order paid.

**Fulfillment:** `unfulfilled → processing → shipped → delivered`.

## Checkout algorithm

1. Authenticate the caller (DRF `IsAuthenticated`).
2. Validate address and idempotency key.
3. Open `transaction.atomic()`.
4. Claim `(user, idempotency_key)` with a unique insert; on collision, lock
   the existing row. Same key + same fingerprint returns the original order.
   Same key + different fingerprint → conflict.
5. Lock the user's cart (`select_for_update`). Reject missing, foreign, empty,
   or non-active carts.
6. Lock cart items.
7. Lock variants in primary-key order.
8. Recalculate unit prices from the catalog (active discount window).
9. Deduct `ProductVariant.stock` (conditional `UPDATE … WHERE stock >= qty`).
10. Insert `Order` and `OrderItem` snapshots.
11. Set cart `status=checked_out`.
12. Mark the idempotency row succeeded and commit.

No HTTP calls, email, or payment-provider I/O run inside this transaction.

### Sequence

```
Client → POST /api/checkout/
      → CheckoutView (auth + serializer)
      → checkout_cart()
           atomic:
             claim idempotency
             lock cart / items / variants
             price + stock deduct
             create order + items
             mark cart checked_out
      ← 201 Order detail (payment_status=unpaid)
```

## Inventory concurrency

**Strategy B — deduct at checkout, restore on cancel.**

Stock is the existing `ProductVariant.stock` integer. There is no separate
reservation table. Locks are acquired in `pk` order to reduce deadlocks.
Oversell is prevented by row locks plus `stock >= quantity` updates.

On cancel, stock is added back once (`inventory_restored`).

Limitation: Django `TestCase` wraps tests in a transaction, so true parallel
lock tests use `TransactionTestCase` against PostgreSQL (this project's engine).

## Idempotency

- Key is required (body `idempotency_key` or header `Idempotency-Key`).
- Scoped to the authenticated user.
- Uniqueness is a database constraint, not an in-memory map.
- Because the claim row is not committed until checkout succeeds, a crash
  during checkout rolls back the claim and a retry with the same key may
  proceed. After a successful commit, retries return the original order.

## Cancellation

Customer (owner) or staff. Eligible when order is `pending` or `confirmed`
and fulfillment is `unfulfilled`.

Does **not** call a payment provider. If `payment_status=paid`, it stays
`paid`. Refunds belong to Payments.

## Address snapshots

There is no saved-address model in this project. Checkout accepts a shipping
address object, validates required fields, and stores a JSON snapshot.
Later edits to a customer's profile cannot change past orders.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/checkout/` | Create order from cart |
| `GET` | `/api/orders/` | List current user's orders (no line items) |
| `GET` | `/api/orders/<uuid>/` | Order detail with items |
| `POST` | `/api/orders/<uuid>/cancel/` | Cancel if eligible |

All endpoints require authentication. Querysets are scoped to `request.user`
(cancel also allows staff). Protected fields cannot be written by customers;
there is no order update API.

### Checkout body

```json
{
  "idempotency_key": "client-generated-stable-key",
  "cart_id": 1,
  "shipping_address": {
    "full_name": "Alice Example",
    "line1": "1 High Street",
    "line2": "",
    "city": "London",
    "state": "",
    "postal_code": "SW1A 1AA",
    "country": "GB",
    "phone": ""
  }
}
```

`cart_id` is optional; the active cart is used when omitted. Ownership is
always verified. Client prices are ignored.

### Error handling

Domain errors return `{"detail": "..."}` with 400, 404, or 409. Internal
exceptions are not converted to generic 500 payloads by this app.

## Pricing

`subtotal = Σ(unit_price × quantity)`
`total = subtotal + shipping_fee + tax_amount - discount_amount`

Shipping and tax are **0.00** — the catalog has no rates. Variant discount
windows are applied as the unit price; they are not also stored as
`discount_amount`. Price changes between add-to-cart and checkout use the
price at checkout time.

Rounding: `ROUND_HALF_UP` to two decimal places (same as `ProductVariant.price`).

## Testing

From `backend/`:

```bash
python manage.py test project_apps.orders --verbosity=2
```

Requires the configured PostgreSQL database (see `compose.yaml`).

## Payments next (do not redesign Orders)

Implement a separate `payments` app that:

1. Creates payment attempts **after** an `Order` exists (`order_id` FK).
2. Talks to the provider **outside** the checkout transaction.
3. Verifies webhooks itself.
4. Calls `record_verified_payment_result(order_id=..., result="paid"|"failed"|"refunded"|"pending")`.

Do not let customers `PATCH` `payment_status`. Do not import Orders from
Payments and Payments from Orders in a cycle — Payments should depend on
Orders, not the reverse. `record_verified_payment_result` lives in
`project_apps.orders.services` as the stable boundary.

`paid` confirms a pending order. `failed` does not delete the order.
`refunded` does not un-ship goods or auto-cancel.

## Known limitations

- No tax, shipping-rate, or coupon engine.
- No saved address book.
- Currency is a stored code only; no multi-currency conversion or per-currency scale.
- No email/outbox; `transaction.on_commit` is unused because there are no side effects yet.
- Staff fulfillment transitions exist as service functions, not public HTTP endpoints.
