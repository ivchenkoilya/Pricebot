# Clarify 1.0 — Product Upgrade

Clarify 1.0 turns the Telegram Mini App into a more complete mobile AI workspace without changing the existing user database or bot architecture.

## Mini App

- new `AppV1.tsx` mobile-first interface;
- new `v1.css` visual system with unified spacing, typography, cards and states;
- Lucide SVG icon system instead of navigation Unicode symbols and most UI emoji;
- compact glass bottom dock with `House`, `Brain`, `Plus`, `Sparkles`, `UserRound`;
- official supplied Clarify banner remains the brand asset;
- responsive material type grid without horizontal clipping;
- redesigned internal material composer / bottom sheet;
- real processing states for material intake;
- home dashboard with recent materials and useful stats;
- redesigned quick actions with clearer hierarchy;
- redesigned Memory, Material Detail, Projects, Compare, Reminders, Write with Clarify and Profile;
- destructive data deletion now requires an explicit confirmation modal;
- OWNER usage displays `Unlimited` instead of a fake progress bar;
- skeleton states and lightweight transitions.

## Memory 2.0

Memory now ranks a wider pool of recent materials by lexical relevance before building AI context. It no longer sends a long list of unrelated recent materials merely because they were recent.

The Memory response returns only the selected source materials, including their material ids so the Mini App can open them directly. The UI initially shows up to three sources and lets the user expand the list.

## Voice performance

The existing fast STT path remains the default:

- `faster-whisper`;
- `tiny` model;
- int8 CPU inference;
- model prewarm;
- 16 kHz mono preprocessing for long audio;
- long-audio chunking;
- parallel chunk decoding;
- no beam-search overhead.

Clarify 1.0 additionally logs STT model-load and transcription latency (`audio_seconds`, `chunks`, `parallel`, `split_ms`, `elapsed_ms`) without logging transcript contents. This makes the real Amvera bottleneck measurable.

## Telegram `/start`

`/start` is simplified to two messages:

1. official Clarify banner;
2. short introduction with Open Clarify / Capabilities / Examples / Help buttons.

Banner failure never prevents the text start message from being delivered.

## Compatibility

Clarify 1.0 keeps:

- the existing SQLite database;
- materials and projects;
- reminders;
- Telegram Stars / PRO;
- OWNER access;
- documents, images, voice and audio;
- links and video-link workflows;
- conversation context;
- Amvera deployment;
- existing FastAPI API routes.

No destructive database migration is required.
