# Webhooks guide

_Section: Developers_ · _Last updated: 2025-08-18_

Paperkite sends events to your endpoint as signed HTTPS POST requests.

- The signature is in the `Paperkite-Signature` header, computed with HMAC-SHA256.
- Reject requests whose timestamp is more than 5 minutes old.
- Respond with any 2xx status within 10 seconds.
- Failed deliveries are retried up to 8 times over 24 hours with exponential backoff.
