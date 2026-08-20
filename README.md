# Clarify 0.6.0 — MINI APP

**Send anything. Get clarity.**

Clarify — Telegram AI-инбокс: пользователь пересылает голосовое, документ, фото, скриншот, ссылку или переписку и получает суть, задачи, сроки, суммы, риски и следующие действия. Версия 0.6 добавляет полноценное Telegram Mini App поверх существующего бота.

Это продолжение существующего `Pricebot`, а не новый проект. Сохраняются `/data/price.db`, пользователи, материалы, проекты, PRO/Stars, owner-доступ, Amvera и legacy-модули.

## Clarify 0.6

### Новый `/start`

`/start` отправляет фирменный баннер `assets/clarify_banner.webp`, короткое коммерческое приветствие и inline-действия:

- 🚀 Открыть Clarify;
- 📎 Разобрать;
- 🧠 Мои материалы;
- 👑 PRO;
- ❓ Как пользоваться.

Если `WEBAPP_URL` не настроен, бот не падает: WebApp-кнопка просто не показывается.

### Telegram Mini App

Frontend находится в `webapp/` и использует React + Vite + TypeScript без тяжёлого UI-фреймворка. Production build раздаётся тем же FastAPI по `/app/`, поэтому не нужен второй сервер.

Основные экраны:

- Home — hero Clarify, быстрые действия и переход в чат;
- Materials — поиск, фильтры и история;
- Material Details — выжимка, AI-действия, Q&A и источники страниц;
- Projects — рабочие темы и Q&A сразу по нескольким материалам;
- Compare — сравнение двух материалов;
- Reminders — создание и управление напоминаниями;
- Write for me — генерация и переписывание в пользовательском стиле;
- PRO — Telegram Stars;
- Profile / Settings — timezone, style, Fast/Smart режим, удаление данных;
- OWNER — отдельное отображение `OWNER · Unlimited`, без предложения купить PRO.

## Архитектура

```text
main.py                         FastAPI + Telegram polling + scheduler
assets/
  clarify_banner.webp           оптимизированный фирменный баннер
app/
  webapp/
    auth.py                     Telegram initData validation
    api.py                      Mini App REST API
  bot/
    clarify_start.py            новый /start + WebApp button
    clarify_web.py              ссылки
    clarify_context.py          контекст/vision follow-up
    razberi_*.py                существующие bot routers
  ai/                           intent/context/provider
  database/                     существующая SQLite схема
  processors/                   docs/STT/chunking
  services/                     materials/projects/reminders/subscriptions
webapp/
  src/
    App.tsx
    api.ts
    styles.css
  package.json
  vite.config.ts
```

## Telegram WebApp auth

Frontend **не передаёт доверенный `user_id`**. Каждый API-запрос отправляет Telegram `initData`:

```http
Authorization: tma <Telegram WebApp initData>
```

Backend проверяет:

1. `hash` через HMAC-SHA256 и `BOT_TOKEN`;
2. `auth_date` и максимальный возраст;
3. Telegram `user` payload;
4. после этого находит/создаёт пользователя по проверенному Telegram ID.

Все запросы материалов/проектов/напоминаний дополнительно фильтруются по `user.id`. Зная чужой material ID, получить его нельзя.

Для локального тестирования существует `WEBAPP_DEV_AUTH`, но в production он должен быть `false`.

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

AI Q&A использует тот же OpenAI-compatible provider, quota, retrieval и существующие chunks, что и Telegram-бот. Второго AI pipeline нет.

## PDF sources

PDF хранит маркеры вида:

```text
[Страница 7]
```

При Q&A Mini App извлекает только страницы, реально присутствующие в retrieved-контексте, и показывает их как источники. Номер страницы не придумывается frontend-ом.

## OWNER

`ADMIN_TELEGRAM_ID` — единственный источник owner-статуса.

Owner:

- автоматически получает internal PRO;
- не имеет дневного AI-лимита;
- отображается как `OWNER · Unlimited`;
- не видит клиентский usage-limit;
- не получает предложение купить PRO;
- не создаёт фиктивных Stars-платежей.

## Environment

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

Если frontend и API работают с одного Amvera origin, `WEBAPP_CORS_ORIGINS` оставляется пустым. Если Mini App размещён отдельно, укажите только конкретные HTTPS-origin через запятую — не используйте `*`.

## BotFather / Web App

После первого production deploy:

1. убедитесь, что `https://YOUR-AMVERA-DOMAIN/app/` открывается по HTTPS;
2. задайте этот адрес в `WEBAPP_URL` на Amvera;
3. redeploy/restart контейнера;
4. при необходимости настройте Web App domain/menu button через BotFather;
5. `/start` автоматически покажет кнопку `🚀 Открыть Clarify`.

Сам backend всё равно проверяет `initData`, поэтому одного доверия домену BotFather недостаточно.

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

Vite proxy направляет `/api` и `/assets` на `127.0.0.1:8080`.

Для ручной разработки вне Telegram можно временно включить:

```env
TEST_MODE=true
WEBAPP_DEV_AUTH=true
```

и передавать `X-Dev-Telegram-User`. В production `WEBAPP_DEV_AUTH=false`.

## Production Docker / Amvera

Dockerfile multi-stage:

```text
node:22-alpine
  -> npm install
  -> npm run build
  -> /webapp/dist

python:3.12-slim
  -> Python dependencies
  -> bot/backend
  -> copy webapp/dist
  -> python main.py
```

`amvera.yaml` продолжает использовать один контейнер, порт `8080` и persistent mount `/data`.

База остаётся:

```env
DATABASE_URL=sqlite+aiosqlite:////data/price.db
```

Новая отдельная база для Mini App не создаётся.

## CI

GitHub Actions обязан пройти:

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

`/ready` дополнительно показывает, присутствует ли production WebApp build.

## Privacy and security

- `BOT_TOKEN` и AI keys только в environment variables;
- сайты, документы, изображения и сообщения считаются untrusted content;
- prompt injection внутри материала не становится системной инструкцией;
- API не принимает client-supplied Telegram ID как identity;
- URL reader не обходит CAPTCHA/login/access control;
- `/delete_my_data` и Mini App privacy action удаляют материалы, chunks, проекты, style, reminders и usage согласно текущей логике;
- финансовые записи сохраняются там, где нужны для корректного Stars-учёта;
- traceback пользователю не показывается.

## Что осталось от Pricebot

Legacy PRICE-модули намеренно остаются в репозитории для совместимости/истории. Runtime Clarify использует существующую инфраструктуру и базу, но не запускает старый price-tracking UX как основной интерфейс.
