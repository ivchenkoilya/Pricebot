# PRICE 0.1.0

**PRICE** — Telegram-бот для отслеживания реальных цен.

> Скинь товар. Я скажу, когда покупать.

Пользователь отправляет ссылку на товар. PRICE пытается достоверно извлечь название и цену, сохраняет историю, создаёт одно общее представление товара для всех пользователей и периодически перепроверяет источник. Если цена действительно снизилась или выполнилось условие пользователя, бот присылает уведомление.

## Что умеет

- принимать обычные HTTP/HTTPS-ссылки на товары;
- удалять безопасные marketing-параметры вроде `utm_source`, не ломая параметры товара;
- искать данные в JSON-LD `Product`, schema/microdata, product meta tags и HTML price blocks;
- использовать confidence-порог, а не принимать первое число на странице за цену;
- честно сохранять недоступный источник без выдуманной цены;
- хранить свою историю цены и не считать зачёркнутую магазином цену реальным историческим падением;
- отслеживать существенное падение, целевую цену, процент снижения, новый минимум и возврат в наличие;
- не спамить одинаковыми alert благодаря cooldown и дедупликации;
- проверять один `Product` один раз, даже если за ним следят разные пользователи;
- FREE/PRO лимиты из environment variables;
- Telegram Stars subscription для PRICE PRO;
- опциональный OpenAI-слой для понимания обычных текстовых запросов о товарах;
- `/health`, `/status`, `/id`, `/ai_status`, `/paysupport`, `/cancelpro`;
- admin `/stats`, `/test`, `/refund`;
- SQLite на persistent volume Amvera;
- GitHub Actions: compile, pytest и Docker build.

## Важное ограничение 0.1.0

PRICE не обходит CAPTCHA, авторизацию и антибот-защиту. Некоторые магазины могут запрещать автоматическое чтение страницы или отдавать цену только после JavaScript/API-запросов. В таком случае бот пишет, что источник временно недоступен, сохраняет ссылку и не придумывает цену.

`🔎 Найти дешевле` в 0.1.0 не изображает глобальный поиск по всему интернету. Архитектура нормализации товара подготовлена для дальнейших provider adapters и сопоставления бренд/модель/GTIN.

## Структура

```text
app/
  bot/              Telegram handlers, keyboards, middleware
  config/           environment settings
  database/         SQLAlchemy models/session
  payments/         Telegram Stars
  scheduler/        batch price checks
  services/         products, alerts, stats, affiliate placeholder, optional AI
  trackers/         provider interface + GenericProvider/OzonProvider
  utils/            URL/SSRF, money, rate limit
tests/
main.py
Dockerfile
amvera.yaml
.env.example
.github/workflows/test.yml
```

## Локальный запуск

Нужен Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

В `.env` укажите минимум:

```env
BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
ADMIN_TELEGRAM_ID=
```

Запуск:

```bash
python main.py
```

Проверка HTTP:

```text
GET /health
```

Ответ:

```json
{"status":"ok","app":"PRICE","version":"0.1.0"}
```

## Переменные окружения

Основные значения есть в `.env.example`:

- `BOT_TOKEN` — секретный токен Telegram-бота; никогда не коммитить;
- `ADMIN_TELEGRAM_ID` — необязательный Telegram ID владельца;
- `TEST_MODE=true` — включает тестовый сценарий для владельца;
- `DATABASE_URL` — пустое значение выбирает SQLite автоматически;
- `PORT=8080`;
- `SERVE_HTTP=true`;
- `DEFAULT_TIMEZONE=Europe/Moscow`;
- `CHECK_INTERVAL_FREE_HOURS=12`;
- `CHECK_INTERVAL_PRO_HOURS=2`;
- `FREE_WATCH_LIMIT=3`;
- `PRO_WATCH_LIMIT=50`;
- `PRO_STARS_PRICE=199`;
- `REQUEST_TIMEOUT=20`;
- `MAX_PROVIDER_FAILURES=5`;
- `MIN_DROP_PERCENT=3`;
- `ALERT_COOLDOWN_HOURS=6`;
- fetch/user rate-limit параметры;
- `DISABLED_PROVIDERS` — список отключённых provider через запятую;
- `AI_ENABLED=true` — включает опциональный AI-слой;
- `OPENAI_API_KEY` — секрет OpenAI Platform, хранить только в Amvera Secrets;
- `OPENAI_MODEL=gpt-5-mini` — модель для нормализации товарных запросов.

На Amvera при пустом `DATABASE_URL` приложение использует:

```text
sqlite+aiosqlite:////data/price.db
```

Локально — `./data/price.db`.

## GitHub

`.env`, SQLite-файлы, локальные окружения и caches находятся в `.gitignore`. В репозитории должен лежать только `.env.example` без реальных секретов.

Workflow `.github/workflows/test.yml` на push/PR выполняет:

1. Python 3.12;
2. установку зависимостей;
3. `compileall`;
4. `pytest`;
5. `docker build`.

## Amvera

Проект использует Docker. Файл `amvera.yaml` задаёт Docker environment, `persistenceMount: /data` и `containerPort: 8080`.

### Развёртывание только с Android-телефона

1. Открой Amvera и создай приложение.
2. Подключи GitHub repository `ivchenkoilya/Pricebot`.
3. Выбери ветку `main`.
4. В Variables/Secrets добавь `BOT_TOKEN`.
5. Если нужен TEST PANEL владельца, добавь `ADMIN_TELEGRAM_ID`.
6. Для AI добавь секрет `OPENAI_API_KEY` и оставь `AI_ENABLED=true`.
7. Запусти build/deploy либо дождись автоматической сборки после push из GitHub.
8. Открой Build Logs и убедись, что контейнер стартовал без traceback.
9. Открой Telegram и отправь боту `/status`.
10. Для проверки AI отправь `/ai_status`.
11. Пришли ссылку на реальный товар и нажми `🔔 Следить`.

Компьютер после deployment не нужен: polling, scheduler и HTTP health работают внутри контейнера.

### Проверка OpenAI

После добавления `OPENAI_API_KEY` и нового deployment:

```text
/ai_status
```

Должно вернуть `AI: ON`. Затем можно написать обычным текстом, например:

```text
айфон 16 про 256 чёрный
```

PRICE нормализует товарный запрос, но не придумывает цену. Реальную цену по-прежнему получает provider магазина.

## Первая проверка после deployment

### TEST 1 — status

Отправить:

```text
/status
```

Ожидаются Telegram/Database/Scheduler/Tracker и счётчики Products/Watches.

### TEST 2 — реальный URL

Отправить ссылку на страницу товара, которая публично отдаёт structured product data. PRICE должен показать реально найденное название/цену. Если магазин блокирует чтение, бот обязан сообщить об этом, а не выдумать цену.

### TEST 3 — watch

Нажать `🔔 Следить`, затем открыть `🔔 Мои товары`.

### TEST 4 — persistence

Перезапустить приложение Amvera. Товар должен остаться в `🔔 Мои товары`, потому что БД находится в `/data`.

### TEST 5 — alert

При настроенном `ADMIN_TELEGRAM_ID` открыть:

```text
/test
```

Выбрать тестовое падение цены. PRICE создаёт тестовую точку, отправляет alert и восстанавливает реальную текущую цену. Тестовые точки не участвуют в пользовательской min/max истории.

### TEST 6 — FREE

Проверить ограничение `FREE_WATCH_LIMIT`.

### TEST 7 — TEST PRO

В `/test` переключить PRO и проверить увеличенный `PRO_WATCH_LIMIT`, новый минимум и уведомление о наличии.

## PRICE PRO / Telegram Stars

PRO оформляется внутри Telegram за Stars (`XTR`). Цена задаётся только через `PRO_STARS_PRICE`. Код не привязан к конкретным 199 Stars.

Поддерживаются:

- invoice link;
- pre-checkout validation;
- `successful_payment`;
- сохранение `telegram_payment_charge_id`;
- активация и продление PRO;
- отмена будущего автопродления через `/cancelpro`;
- `/paysupport`;
- admin refund `/refund TELEGRAM_ID CHARGE_ID`;
- событие возврата Stars.

## Безопасность

PRICE проверяет URL до запроса и после каждого redirect. Блокируются localhost, private/loopback/link-local/reserved/multicast/unspecified IPv4/IPv6 и DNS-имена, которые резолвятся во внутренний адрес. Есть user/global/per-host ограничения запросов и максимальный размер HTML-ответа.

Бот не логирует `BOT_TOKEN` или `OPENAI_API_KEY`. Не добавляйте cookies, токены GitHub, Amvera secrets или закрытые API credentials в исходники.

## Если цена не определяется

Порядок действий:

1. проверить логи provider;
2. убедиться, что страница публично доступна без CAPTCHA/login;
3. проверить JSON-LD/schema/meta данные страницы;
4. при необходимости добавить отдельный разрешённый provider adapter;
5. не снижать confidence просто ради того, чтобы показать пользователю любое число.

## Версия

`PRICE 0.1.0` — production MVP. Главный сценарий: ссылка → реальная цена → watch → scheduler → реальное изменение → уведомление.
