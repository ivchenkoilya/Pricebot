# Clarify 0.7.0 — START + CONVERSATION

**Send anything. Get clarity.**

Clarify — Telegram AI-помощник, который принимает сообщения, голосовые, документы, фото, скриншоты и ссылки, выделяет главное и позволяет продолжать разговор уточняющими вопросами.

Это продолжение существующего `Pricebot`, а не новый проект. Сохраняются `/data/price.db`, пользователи, материалы, проекты, PRO/Stars, OWNER-доступ, Mini App, Amvera и legacy-модули.

## Что нового в Clarify 0.7

### Новый `/start`

`/start` теперь сначала отправляет фирменный баннер `assets/clarify_banner.webp`, а затем отдельное приветствие:

> Привет! Я Clarify 👋

Стартовый экран сразу объясняет, что Clarify умеет работать с:

- 🎤 голосовыми;
- 📄 документами;
- 🖼 скриншотами и изображениями;
- 💬 сообщениями и текстом;
- 🔗 ссылками;
- 📌 ключевыми фактами, сроками и действиями;
- ❓ уточняющими вопросами по присланному материалу;
- 🧠 объяснением сложного простыми словами.

Баннер отправляется безопасно: если Telegram временно не сможет принять изображение, текстовый `/start` всё равно продолжит работать.

### Кнопки стартового экрана

Под приветствием доступны:

- `✨ Что умеет Clarify`;
- `💡 Примеры`;
- `❓ Помощь`;
- `🧠 Как это работает`;
- `🗑 Очистить контекст`;
- `🚀 Открыть Clarify`, если настроен HTTPS `WEBAPP_URL`.

Повторный `/start` не очищает текущий контекст.

### Обычный диалог

Короткие пользовательские фразы больше не обязаны превращаться в новый «материал».

Clarify локально, без лишнего AI-запроса, понимает типичные intents:

- `Привет` / `Здравствуйте` / `Hello`;
- `Кто ты?`;
- `Что ты умеешь?`;
- `Как пользоваться?`;
- `Покажи примеры`;
- короткие фразы вроде `Как дела?`, `Спасибо`, `Понятно`.

Официальное имя продукта во всех пользовательских ответах — **Clarify**.

### Уточняющие вопросы и активный контекст

После разбора материала пользователь может продолжить обычным языком:

- `А какой там срок?`;
- `Что от меня требуется?`;
- `Объясни второй пункт`;
- `Сделай короче`;
- `Какие риски?`;
- `В какой маске этот человек?`;
- `Что у него в руках?`.

Для изображений Clarify при возможности повторно использует сохранённый Telegram `file_id` и задаёт vision-модели именно новый вопрос. Для документов и текста используется retrieval по сохранённым chunks, а не повторное распознавание всего файла.

Короткие вопросы не должны создавать бессмысленную запись «Материал добавлен».

### `/clear`

Команда `/clear` и кнопка `🗑 Очистить контекст` сбрасывают активную разговорную тему, но **не удаляют историю материалов и статистику**.

Реализация использует `ConversationContextService` и отдельный persistent cutoff в таблице `clarify_conversation_states`. Поэтому очистка сохраняется после перезапуска приложения.

После `/clear` старые материалы остаются в `Мои материалы`, но больше не используются автоматически для фраз вроде `А какой срок?`. Новый присланный материал становится новым активным контекстом.

### Telegram command menu

При запуске Clarify настраивает стандартное меню Telegram:

```text
/start    Начать работу
/help     Помощь
/about    О Clarify
/examples Примеры запросов
/summary  Кратко о последнем материале
/clear    Очистить контекст
```

Ошибка настройки меню Telegram не блокирует запуск бота.

### Быстрые действия после разбора

Основные кнопки материала унифицированы:

- `⚡ Кратко`;
- `📌 Главное`;
- `🧠 Простыми словами`;
- `✅ Что делать`;
- `⚠️ Риски`;
- `❓ Задать вопрос`.

Для документов дополнительно остаются деньги и сроки, для голосовых/пересланных сообщений — «что от меня хотят» и готовый ответ. Проекты, исходник, напоминания и удаление также сохранены.

## Telegram Mini App

Frontend находится в `webapp/` и использует React + Vite + TypeScript. Production build раздаётся тем же FastAPI по `/app/`, поэтому второй сервер не нужен.

Основные экраны:

- Home;
- Materials + search/filters;
- Material Details + AI Q&A/actions/sources;
- Projects + project Q&A;
- Compare;
- Reminders;
- Write for me;
- PRO + Telegram Stars;
- Profile / Settings;
- OWNER state.

## Архитектура

```text
main.py                         FastAPI + Telegram polling + scheduler + BotCommand
assets/
  clarify_banner.webp           фирменный баннер
app/
  bot/
    clarify_start.py            /start, help/about/examples/summary/clear
    clarify_chat.py             приветствия, about/capabilities и small talk
    clarify_context.py          follow-up и повторный vision
    clarify_web.py              ссылки
    razberi_*.py                существующие bot routers
  ai/
    intent.py                   локальный intent router
    context.py                  visual follow-up selection
    conversation.py             выбор релевантных материалов
    provider.py                 общий OpenAI-compatible AI pipeline
  database/
    razberi_models.py           материалы + conversation state
  services/
    conversation_context.py     активный контекст и persistent /clear
    core.py                     материалы/projects/usage/privacy
  processors/                   docs/STT/chunking
  webapp/                       Mini App API/auth
webapp/                         React/Vite frontend
```

## Как хранится контекст

Полные документы не копируются в бесконечную chat-history.

Clarify использует:

1. сохранённый последний/релевантный материал;
2. его summary и retrieved chunks;
3. максимум несколько недавних реплик только для разрешения слов вроде `он`, `это`, `там`, `второй`;
4. persistent timestamp последнего `/clear`.

Материалы разных пользователей всегда выбираются по внутреннему `user.id` и не смешиваются.

## Telegram WebApp auth

Frontend **не передаёт доверенный `user_id`**. Каждый API-запрос отправляет Telegram `initData`:

```http
Authorization: tma <Telegram WebApp initData>
```

Backend проверяет HMAC, `auth_date`, подписанный Telegram user payload и после этого ограничивает материалы/проекты/напоминания текущим пользователем.

Для локальной разработки существует `WEBAPP_DEV_AUTH`; в production он должен быть `false`.

## Mini App API

Основные endpoints:

```text
GET    /api/me
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

Telegram и Mini App используют один AI/retrieval/quota pipeline.

## PDF sources

PDF может хранить маркеры вида:

```text
[Страница 7]
```

При Q&A Clarify просит модель указывать страницу только тогда, когда соответствующий маркер действительно присутствует в retrieved-контексте.

## OWNER

`ADMIN_TELEGRAM_ID` — единственный источник OWNER-статуса.

Owner:

- автоматически получает internal PRO;
- не имеет дневного AI-лимита;
- отображается как `OWNER · Unlimited`;
- не получает предложение купить PRO;
- не создаёт фиктивных Stars-платежей.

## Environment

Новых обязательных env-переменных для 0.7 нет.

Минимальный production-набор:

```env
BOT_TOKEN=...
ADMIN_TELEGRAM_ID=...
OPENAI_API_KEY=...
OPENAI_BASE_URL=...
OPENAI_MODEL=...
DATABASE_URL=sqlite+aiosqlite:////data/price.db
DATA_DIR=/data
PORT=8080
SERVE_HTTP=true
WEBAPP_URL=https://YOUR-AMVERA-DOMAIN/app/
WEBAPP_AUTH_MAX_AGE_SECONDS=86400
WEBAPP_DEV_AUTH=false
```

Отдельные модели опциональны:

```env
FAST_MODEL=
SMART_MODEL=
VISION_MODEL=
```

## Local development

Backend:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

Frontend:

```bash
cd webapp
npm install
npm run dev
```

## Production Docker / Amvera

Dockerfile остаётся multi-stage Node 22 → Python 3.12. `amvera.yaml` использует один контейнер, порт `8080` и persistent mount `/data`.

База остаётся:

```env
DATABASE_URL=sqlite+aiosqlite:////data/price.db
```

Новая таблица `clarify_conversation_states` создаётся автоматически через существующий `Base.metadata.create_all`; отдельная ручная миграция не требуется для текущей SQLite-схемы.

## CI

GitHub Actions проверяет:

```text
Python dependencies
Mini App dependencies
Python compile
pytest
TypeScript check
Vite production build
Docker production build
```

## Health

```text
GET /health
GET /ready
```

## Privacy and security

- `BOT_TOKEN` и AI keys хранятся только в environment variables;
- сайты, документы, изображения и сообщения считаются untrusted content;
- prompt injection внутри материала не становится системной инструкцией;
- API не доверяет client-supplied Telegram ID;
- URL reader не обходит CAPTCHA/login/access control;
- `/clear` только сбрасывает активный контекст и не удаляет историю;
- `/delete_my_data` остаётся отдельным действием для удаления пользовательских данных;
- traceback пользователю не показывается.

## Совместимость

Clarify 0.7 сохраняет существующие:

- голосовые и STT;
- изображения/vision;
- PDF/DOCX/TXT/MD/XLSX/CSV;
- ссылки;
- проекты и сравнение;
- PRO/Telegram Stars;
- OWNER unlimited;
- Mini App;
- Docker/Amvera;
- legacy Pricebot-модули.
