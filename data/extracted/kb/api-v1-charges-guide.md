# Creating a charge

_Section: Developers_

Use the Charges API to take a payment.

1. Send `POST /v1/charges` with `amount`, `currency` and `source`.
2. Read the `status` field of the response.
3. Use `POST /v1/charges/{id}/refund` to refund.

Charges are the primary way to accept payments.
