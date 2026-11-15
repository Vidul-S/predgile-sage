# Verifying webhook signatures

_Section: Developers_

- The signature is in the `X-Paperkite-Sig` header, computed with HMAC-SHA1.
- Reject requests older than 10 minutes.
