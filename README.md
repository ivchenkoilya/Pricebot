# Clarify 0.9.0 — Premium AI Workspace

**Send anything. Get clarity.**

Clarify — Telegram AI Workspace, который принимает текст, голосовые, аудио, документы, изображения, скриншоты и ссылки, сохраняет материалы в личную Memory и помогает быстро получить суть, факты, задачи, сроки, суммы, риски и ответы на вопросы.

Проект продолжает существующий `Pricebot`: сохраняются текущая база `/data/price.db`, пользователи, материалы, проекты, PRO/Stars, OWNER-доступ, Amvera deployment и legacy-модули.

## Главное в 0.9.0

### Полный редизайн Mini App

Mini App переведён на новый premium dark UI:

- Deep Navy + Electric Blue + Purple Glow;
- новый hero-экран и фирменный баннер;
- glass-карточки и mobile-first типографика;
- новый bottom navigation;
- центральная кнопка `＋` для добавления материала;
- onboarding для первого запуска;
- loading / processing / empty / success / error states;
- safe-area поддержка для Telegram WebView на Android.

Основные разделы:

- **Home** — hero, быстрые форматы, недавние материалы, quick actions;
- **Memory** — история материалов, фильтры и AI-поиск по сохранённым знаниям;
- **Projects** — рабочие темы и вопросы по нескольким материалам;
- **AI** — `Написать за меня` и быстрые rewrite-режимы;
- **Profile** — план, статистика, использование AI и настройки.

## Добавление материала прямо из Mini App

Кнопка `Добавить материал` больше не закрывает Mini App и не отправляет пользователя обратно в чат.

Внутри приложения открывается bottom sheet с вариантами:

- 🎤 голос / аудио;
- 📄 документ;
- 🖼 фото / скриншот;
- 🔗 ссылка;
- ✍️ текст.

После выбора материал реально отправляется в backend, обрабатывается существующим Clarify AI pipeline, сохраняется в базе и сразу открывается как результат.

### Новые intake endpoints

```text
POST /api/intake/text
POST /api/intake/link
POST /api/intake/file
```

`/api/intake/file` поддерживает:

```text
Images:    JPG, JPEG, PNG, WEBP
Audio:     MP3, WAV, M4A, OGG, OPUS, WEBM, AAC, FLAC
Documents: PDF, DOCX, TXT, MD, XLSX, CSV
```

Для документов используются существующие FREE/PRO page limits, для файлов — `MAX_FILE_SIZE_MB`.

## Clarify Memory

Memory — единая история материалов пользователя.

Новый endpoint:

```text
POST /api/memory/ask
```

Пример:

> Что я изучал про маркетинг?

Clarify собирает релевантный контекст из последних материалов, отвечает на основе сохранённых данных и показывает использованные источники.

## Новый экран результата

После обработки материала доступны:

- ✨ Кратко;
- 📌 Главное;
- ✅ Что делать;
- ⚠️ Риски;
- 💰 Деньги;
- 📅 Сроки;
- 🧠 Объяснить;
- 🎯 Что хотят;
- собственный вопрос по материалу.

Исходный текст остаётся доступен в раскрывающемся блоке.

## Исправление баннера

Старые бинарные `assets/clarify_banner.*` оказались ненадёжными для Telegram/WebView. В 0.9.0 баннер генерируется сервером как валидный JPEG через Pillow.

Один и тот же валидный баннер используется:

- при `/start` через `BufferedInputFile`;
- в Mini App через `/assets/clarify-banner.webp` или `/assets/clarify-banner.jpg`.

Поэтому `/start` больше не зависит от повреждённого файла на диске, а Mini App не должен показывать broken-image placeholder.

## `/start`

Команда `/start`:

1. отправляет фирменный баннер;
2. показывает короткое позиционирование Clarify;
3. предлагает открыть Mini App;
4. показывает возможности, примеры, помощь и очистку контекста.

Если отправка фотографии Telegram временно не сработает, приветствие и кнопки всё равно продолжают отправляться.

## Profile stats

Новый endpoint:

```text
GET /api/profile/stats
```

Профиль показывает:

- количество материалов;
- проекты;
- активные напоминания в API;
- число AI-запросов за сегодня;
- FREE / PRO / OWNER состояние.

## Telegram WebApp auth

Frontend не доверяет client-side `user_id`.

Каждый API-запрос отправляет подписанный Telegram `initData`:

```http
Authorization: tma <Telegram WebApp initData>
```

Backend проверяет Telegram подпись и ограничивает материалы, проекты, настройки и Memory текущим пользователем.

## Архитектура

```text
main.py                         FastAPI + Telegram polling + scheduler
app/
  brand.py                      runtime-generated Clarify JPEG banner
  bot/
    clarify_start.py            /start / help / about / examples / clear
    clarify_context.py          contextual follow-up
    clarify_media_links.py      video-link actions
    clarify_web.py              ordinary public links
    razberi_*.py                Telegram material workflows
  ai/
    provider.py                 OpenAI-compatible AI pipeline
  processors/
    documents.py                PDF/DOCX/TXT/MD/XLSX/CSV
    stt.py                      speech-to-text
    text.py                     text analysis
  services/
    core.py                     users/materials/projects/usage/privacy
    page_reader.py              public web pages
    media_downloader.py         public media helpers
  webapp/
    api.py                      core Mini App API
    intake.py                   direct material upload API
    memory.py                   AI search across Memory
    auth.py                     Telegram initData verification
webapp/
  src/App.tsx                   Mini App product UI
  src/api.ts                    same-origin API client + multipart upload
  src/styles.css                premium design system
```

## Основной Mini App API

```text
GET    /api/me
GET    /api/profile/stats

POST   /api/intake/text
POST   /api/intake/link
POST   /api/intake/file
POST   /api/memory/ask

GET    /api/materials
GET    /api/materials/{id}
POST   /api/materials/{id}/ask
POST   /api/materials/{id}/action
DELETE /api/materials/{id}

GET    /api/projects
POST   /api/projects
GET    /api/projects/{id}
POST   /api/projects/{id}/ask
POST   /api/compare

GET    /api/reminders
POST   /api/reminders
PATCH  /api/reminders/{id}
DELETE /api/reminders/{id}

POST   /api/compose
POST   /api/rewrite

GET    /api/pro
POST   /api/pro/invoice
GET    /api/settings
PATCH  /api/settings
DELETE /api/me/data
```

## Video links

YouTube / Shorts / TikTok media links use the existing media workflow.

На текущем этапе кнопка **скачивания видео** показывает сообщение, что функция появится позже. Транскрипция, AI-разбор и остальные поддерживаемые действия остаются отдельными возможностями.

Для хостингов, где YouTube ограничивает datacenter IP, можно использовать:

```env
MEDIA_PROXY_URL=http://username:password@host:port
```

Не коммить реальные proxy credentials в GitHub.

## Production / Amvera

Production Docker:

1. собирает React/Vite Mini App на Node 22;
2. устанавливает Python dependencies;
3. раздаёт build тем же FastAPI по `/app/`;
4. запускает Telegram polling и HTTP server одним приложением.

Рекомендуемый `WEBAPP_URL`:

```env
WEBAPP_URL=https://pricebot2-ivch.amvera.io/app/
```

После изменений frontend/backend нужен новый Amvera build/deploy.

## Проверки

GitHub Actions workflow на push/PR запускает:

```text
python -m compileall -q app main.py
pytest -q
npm run check --prefix webapp
npm run build --prefix webapp
docker build -t clarify:test .
```

Отдельный тест проверяет, что runtime-generated баннер действительно является валидным JPEG.

## Безопасность

- секреты задаются только environment variables;
- Telegram Mini App user определяется по подписанному `initData`;
- обычные web/video workflows работают только с публичными ресурсами;
- CAPTCHA/login/access controls не обходятся;
- proxy credentials не должны попадать в репозиторий;
- OWNER определяется через `ADMIN_TELEGRAM_ID`.
