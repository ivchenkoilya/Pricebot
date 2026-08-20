# Clarify 0.8 — Video Links

Clarify can treat public video URLs as media instead of ordinary web pages.

Supported first-class platforms:

- YouTube
- YouTube Shorts
- TikTok, including `vm.tiktok.com` and `vt.tiktok.com`

Best-effort routing is also enabled for public Instagram and X/Twitter video URLs supported by `yt-dlp`.

## User actions

When a public media URL is sent without an instruction, Clarify inspects it and shows:

- `⬇️ Скачать видео`
- `🎧 Скачать аудио`
- `📝 Расшифровать`
- `✨ Краткий пересказ`
- `📌 Главное`
- `🧠 Объяснить`

Direct natural-language commands are supported, for example:

- `Скачай это видео <URL>`
- `Скачай аудио mp3 <URL>`
- `Сделай текст из этого <URL>`
- `Кратко расскажи, о чём ролик <URL>`

The transcript is stored as a normal Clarify material, so follow-up questions use the existing conversation/retrieval pipeline.

## Environment

All variables are optional and have defaults:

```env
MEDIA_DOWNLOAD_ENABLED=true
MEDIA_MAX_FILE_MB=100
MEDIA_FREE_MAX_FILE_MB=50
MEDIA_MAX_DURATION_MINUTES=60
MEDIA_FREE_MAX_DURATION_MINUTES=10
MEDIA_VIDEO_MAX_HEIGHT=720
MEDIA_TEMP_DIR=/data/tmp/media
```

OWNER skips the artificial duration restriction. Infrastructure file-size protection still applies.

## Runtime

- `yt-dlp` handles metadata and media download.
- `ffmpeg` handles merge/audio conversion.
- Node.js is available in the runtime for extractors that need a JavaScript runtime.
- Downloaded files live only in `/data/tmp/media` and are deleted in `finally` after sending/transcription.
- No user cookies, passwords, paid-content bypass, private-video bypass, or DRM bypass is used.
