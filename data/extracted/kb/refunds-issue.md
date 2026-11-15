# Issuing refunds

_Section: Payments_ · _Last updated: 2026-03-04_

You can refund any successful payment in full or in part, from the Dashboard or through the API.

## Partial refunds

1. Open **Payments** and select the payment.
2. Choose **Refund**, then **Partial refund**.
3. Enter the amount and an optional reason.
4. Confirm. The refund is created immediately.

You can issue several partial refunds against the same payment until the refunded total equals the original amount. Through the API, call `POST /v2/refunds` with the `payment_id` and an `amount` in minor units.

## Refund windows

- Card payments can be refunded for 180 days after the payment date.
- SEPA Direct Debit and ACH Debit payments can be refunded for 60 days.
- All other payment methods follow the card window.
- Refunds reach the customer's statement in 5–10 business days.

## Fees

Since 1 July 2024 the processing fee charged on the original payment is not returned when you refund it.
