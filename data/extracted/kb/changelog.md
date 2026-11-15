# Product changelog

_Section: Changelog_ · _Last updated: 2026-04-15_

## 2026-04-15
Instant payouts: the fee rises from 1% to 1.5% (minimum €0.50).

## 2026-04-01
Payouts: Scale standard payouts drop from 2 to 1 business day. Payouts outside the EU, UK and US now add 2 business days (previously 3).

## 2026-02-02
Data: API request log retention rises from 30 to 90 days.

## 2026-01-15
API: `/v1/charges` is removed. Requests return 410 Gone.

## 2025-11-03
Subscriptions: the maximum trial length rises from 14 to 30 days.

## 2025-10-06
Subscriptions: proration is now calculated per day (previously on a 30-day month).

## 2025-09-15
API keys: the grace period when rolling a key is shortened from 48 to 24 hours.

## 2025-09-08
Invoices: the attachment size limit rises from 5 MB to 10 MB.

## 2025-08-01
Disputes: the evidence deadline is shortened from 10 to 7 days. The dispute fee drops from €20 to €15.

## 2025-07-01
Currencies: the conversion fee drops from 1.5% to 1.0%.

## 2025-06-17
Smart Retries: failed subscription payments are retried 4 times over 14 days (previously 3 times over 7 days).

## 2025-06-01
Security: two-factor authentication becomes mandatory for team admins. SSO is limited to Scale and Enterprise (previously Pro and above).

## 2025-05-06
Coupons: stacking is removed. One coupon per subscription.

## 2025-03-01
Plans: Basic is renamed Starter and Business is renamed Scale. Rate limits rise: Starter 60 to 100, Pro 500 to 1,000, Scale 2,000 to 5,000 requests per minute. Billing Portal is renamed Customer Portal, Auto Recovery is renamed Smart Retries, and the Charges API is renamed Payments API.

## 2025-01-15
API: `/v1/charges` is deprecated. Sunset date: 15 January 2026. Use `/v2/payments`.

## 2024-10-14
Payouts: instant payouts launch for Pro and Business at 1% (minimum €0.50).

## 2024-07-01
Refunds: processing fees are no longer returned when a payment is refunded.

## 2024-06-30
Webhooks: SHA-1 signatures and the legacy header are removed. All signatures use HMAC-SHA256.

## 2024-03-11
Refunds: the card refund window is extended from 90 to 180 days. Partial refunds are no longer limited to 3 per payment and can be issued from the Dashboard.

## 2023-09-12
Webhooks: the signature header is renamed from `X-Paperkite-Sig` to `Paperkite-Signature`. The old header is sent in parallel until 30 June 2024.
