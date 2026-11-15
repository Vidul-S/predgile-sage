# Payments API

_Section: Developers_ · _Last updated: 2026-02-17_

Create a payment with `POST /v2/payments`.

- Amounts are integers in minor units, for example 2500 for €25.00.
- Send an `Idempotency-Key` header. Keys are valid for 24 hours.
- A payment that needs customer action has the status `requires_action`.
- Use `GET /v2/payments/{id}` to read a payment.
