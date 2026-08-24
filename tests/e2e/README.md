# Clarify Telegram E2E

This directory is an opt-in production/staging smoke-test harness. Normal CI does **not** log into a Telegram user account and does not perform real payments.

## Purpose

The runner can use a dedicated Telegram **test user** (not the bot token) to exercise Clarify like a real person:

- `/start`
- ordinary text
- schemeless links such as `vk.ru`
- voice/photo/document fixtures when paths are provided
- support command
- latency and PASS/FAIL reporting

Payments are intentionally excluded from automatic production E2E.

## Required environment variables

Never commit these values.

```bash
CLARIFY_E2E=1
CLARIFY_E2E_API_ID=123456
CLARIFY_E2E_API_HASH=...
CLARIFY_E2E_SESSION=...
CLARIFY_E2E_BOT_USERNAME=ClarifyTestBot
```

Optional fixture paths:

```bash
CLARIFY_E2E_IMAGE=/absolute/path/screenshot.png
CLARIFY_E2E_VOICE=/absolute/path/voice.ogg
CLARIFY_E2E_DOCUMENT=/absolute/path/test.docx
```

Use a staging bot whenever possible so the runner cannot spam real users or mutate production data unexpectedly.

## Run

Install Telethon only in the QA environment:

```bash
pip install telethon
CLARIFY_E2E=1 pytest -q tests/e2e/test_telegram_smoke.py -s
```

Without `CLARIFY_E2E=1` the suite skips safely.

## Expected report

Each scenario prints one line containing the operation, PASS/FAIL and elapsed time. The test fails if Clarify never answers inside the bounded timeout. Semantic answer-quality checks should use stable fixture facts rather than brittle exact string matching.
