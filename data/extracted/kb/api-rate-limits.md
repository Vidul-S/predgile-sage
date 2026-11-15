# API rate limits

_Section: Developers_ · _Last updated: 2026-02-09_

Rate limits apply per account across all API keys.

- Starter: 100 requests per minute.
- Pro: 1,000 requests per minute.
- Scale: 5,000 requests per minute.
- Enterprise limits are agreed in the contract.

Requests above the limit return HTTP 429 with a `Retry-After` header. Use exponential backoff and idempotency keys when retrying.

Plans formerly called Basic and Business are now Starter and Scale.
