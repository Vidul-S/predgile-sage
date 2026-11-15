# Webhooks troubleshooting FAQ

_Section: Developers_ · _Last updated: 2025-08-25_

## Why did my endpoint stop receiving events?

Paperkite retries failed deliveries up to 5 times over 12 hours. After that the event is marked as failed and you can replay it from the Dashboard.

## How do I test locally?

Use the CLI to forward events to localhost while in test mode.
