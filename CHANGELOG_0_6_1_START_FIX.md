# Clarify 0.6.1 — START reliability fix

- Branded WebP banner is converted to JPEG in memory before Telegram `sendPhoto`.
- `/start` has a text fallback if banner upload fails for any reason.
- Metrics and error logging can no longer make `/start` silent.
- Added regression test for Telegram-safe JPEG conversion.
