# Clarify 0.3.0

**Send anything. Get clarity.**

Clarify — Telegram AI-помощник, который принимает текст, голосовые, документы и скриншоты, выделяет главное и помогает понять, что делать дальше.

Это продолжение существующего `Pricebot`, а не новый проект. Сохраняются GitHub/Amvera-инфраструктура, `/data/price.db`, пользователи, PRO-состояния, платежи и legacy-модули Pricebot. Новые возможности добавляются поверх существующей базы без destructive migration.

## Что нового: 0.2 FAST + 0.3 SMART

### FAST

- обычные запросы идут через `FAST_MODEL`, сложные — через `SMART_MODEL`;
- большие документы анализируются parallel map/reduce с ограниченной конкурентностью;
- вопросы по документам получают только релевантные chunks вместо повторной отправки всего файла;
- скриншот анализируется одним structured vision-запросом вместо двух последовательных AI-запросов;
- изображения уменьшаются и сжимаются перед vision;
- OCR страниц сканированного PDF выполняется параллельно;
- local `faster-whisper` настроен на быстрый decode;
- можно переключить голосовые на OpenAI-compatible remote STT;
- Telegram показывает короткие стадии обработки вместо одного долгого «ждите».

### SMART

- локальный intent router понимает продолжения без отдельного AI-запроса;
- можно писать: `а оплатить когда?`, `а если задержат?`, `что от меня хотят?`, `объясни простыми словами`;
- для документов есть отдельные действия: `⚠️ Риски`, `💰 Деньги`, `📅 Сроки`, `👶 Просто`;
- для голосовых и переписки: `🎯 Что от меня хотят?`, `✍️ Ответить`;
- два материала можно сравнить через `🔀 Сравнить`;
- связанные материалы можно складывать в `📁 Проекты`;
- `/style` сохраняет предпочтительный стиль для «Напиши за меня» и ответов;
- обновлены карточки результатов и главное меню.

## Главное меню

- 📎 Разобрать
- ✍️ Написать
- 🧠 Мои материалы
- 🔀 Сравнить
- 📁 Проекты
- 👑 PRO
- ⚙️ Настройки
- ❓ Помощь

Меню не обязательно: текст, voice, фото и документы можно просто отправлять в чат.

## Поддерживаемые материалы

- обычный и длинный текст;
- Telegram Voice и аудиофайлы;
- PDF, DOCX, TXT, Markdown, XLSX, CSV;
- JPG, JPEG, PNG, WEBP;
- пересланные Telegram-сообщения.

Clarify умеет делать краткое содержание, извлекать задачи, даты, суммы и предупреждения, отвечать по загруженному материалу, готовить ответы, создавать напоминания и сравнивать документы.

## Архитектура

```text
main.py
app/
  ai/
    intent.py             # быстрый локальный intent router
    provider.py           # OpenAI-compatible AI/vision/compare
    schemas.py
  bot/
    razberi_handlers.py   # агрегатор routers; legacy filename сохранён
    razberi_general.py
    razberi_materials.py
    razberi_media.py
    razberi_payments_admin.py
    razberi_keyboards.py
    razberi_middlewares.py
    razberi_states.py
  config/settings.py
  database/
    models.py             # существующие Pricebot таблицы
    razberi_models.py     # additive Clarify/RAZBERI таблицы
    session.py
  processors/
    common.py             # chunking + retrieval
    documents.py
    router.py
    stt.py
    text.py
  services/
    core.py
    reminders.py
    subscriptions.py
  trackers/               # legacy Pricebot сохранён
  payments/               # legacy Pricebot сохранён
```

## Совместимость с текущей базой

На Amvera продолжает использоваться тот же файл:

```env
DATABASE_URL=sqlite+aiosqlite:////data/price.db
```

Существующие таблицы не переименовываются и не удаляются. Clarify 0.3 добавляет новые таблицы:

- `razberi_projects`
- `razberi_project_materials`
- `razberi_user_styles`

Старые Pricebot/RAZBERI таблицы, пользователи, PRO и история остаются на месте.

## AI: fast / smart / vision

Минимальная конфигурация:

```env
AI_ENABLED=true
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://ваш-openai-compatible-endpoint/v1
OPENAI_MODEL=...
FAST_MODEL=...
SMART_MODEL=...
VISION_MODEL=...
```

Если отдельная модель не указана, Clarify использует fallback на `OPENAI_MODEL`.

Рекомендуемая логика:

- `FAST_MODEL` — дешёвая/быстрая модель для обычного текста, простых действий и follow-up;
- `SMART_MODEL` — более сильная модель для рисков, сложных вопросов, сравнения и финального reduce;
- `VISION_MODEL` — модель с поддержкой изображений.

Проверка подключения:

```text
/ai_status
```

## Настройка скорости

Все основные параметры вынесены в env:

```env
FAST_TEXT_CHARS=12000
CHUNK_PARALLELISM=4
RETRIEVAL_CHUNK_LIMIT=5
RECENT_MATERIAL_HOURS=12
IMAGE_MAX_SIDE=1600
IMAGE_JPEG_QUALITY=82
MAX_AI_CONCURRENCY=4
MAX_DOCUMENT_CONCURRENCY=2
```

Если провайдер начинает отвечать rate-limit, уменьшите `CHUNK_PARALLELISM` и `MAX_AI_CONCURRENCY`. Если сервер и API позволяют больше параллельных запросов — значения можно осторожно повысить.

## Голосовые

### Local STT

```env
STT_PROVIDER=local
WHISPER_MODEL=base
WHISPER_COMPUTE_TYPE=int8
```

Модель загружается лениво и кэшируется в persistent `/data/whisper-cache`.

Если CPU Amvera слабый и скорость важнее точности, можно использовать более маленькую Whisper-модель.

### Remote STT

Если OpenAI-compatible endpoint поддерживает audio transcriptions:

```env
STT_PROVIDER=remote
STT_REMOTE_MODEL=whisper-1
STT_REMOTE_TIMEOUT=25
```

Remote режим обычно снимает тяжёлую транскрипцию с CPU приложения. Конкретный Model ID зависит от подключённого API-провайдера.

## Документы и retrieval

PDF сначала читается локально через PyMuPDF. Vision/OCR запускается только для страниц без нормального text layer.

Большой документ режется на chunks. Map-этап выполняется параллельно, а вопрос по документу получает только наиболее релевантные фрагменты. Retrieval знает базовые смысловые связки вроде:

- оплата ↔ платёж / аванс / постоплата;
- штраф ↔ пеня / неустойка / ответственность;
- срок ↔ дата / дедлайн / период;
- доставка ↔ поставка / отгрузка / приёмка.

## Проекты

Нажмите `📁 В проект` у материала. Можно создать, например:

- `Работа`
- `Договор поставки`
- `Закупка №42`
- `Учёба`

Открытие проекта показывает связанные материалы. Таблицы проектов отдельные, поэтому существующие материалы не мигрируются и не повреждаются.

## Сравнение

Нажмите `🔀 Сравнить`, затем отправьте два ID материала, например:

```text
12 15
```

Clarify сравнит ключевые отличия, деньги, сроки, обязательства и риски и не будет объявлять вариант «лучшим», если данных недостаточно.

## Персональный стиль

Команда:

```text
/style
```

Пример профиля:

```text
Коротко, разговорно, без приветствий, без канцелярита, иногда скобочка вместо смайла.
```

Профиль используется для «Напиши за меня» и подходящих вариантов ответа.

## FREE / PRO

```env
FREE_DAILY_AI_LIMIT=10
PRO_DAILY_AI_LIMIT=150
FREE_VOICE_DAILY_LIMIT=3
FREE_VOICE_MAX_SECONDS=120
FREE_DOCUMENT_MAX_PAGES=10
PRO_DOCUMENT_MAX_PAGES=200
PRO_STARS_PRICE=299
```

Telegram Stars, 30-дневная подписка, отмена и служебный refund-механизм сохранены из предыдущей версии.

## Напоминания

Примеры:

```text
напомни завтра оплатить поставщика
напомни через два часа позвонить
напомни в пятницу проверить заказ
```

После подтверждения напоминание хранится в SQLite и переживает restart приложения.

## Приватность

- ключи и `BOT_TOKEN` только через environment variables;
- пользовательские файлы не исполняются;
- есть whitelist расширений и лимит размера;
- содержимое материалов не пишется в обычный лог;
- документы и изображения считаются недоверенными данными и не могут менять system instructions;
- временные файлы удаляются после обработки;
- `/delete_my_data` удаляет материалы, chunks, проекты, стиль, AI usage и напоминания;
- финансовые записи сохраняются для корректного платежного учёта.

## Amvera

В репозитории уже есть `Dockerfile` и `amvera.yaml`. Persistent storage монтируется в `/data`, HTTP health endpoint слушает порт `8080`.

Минимум:

```env
BOT_TOKEN=...
ADMIN_TELEGRAM_ID=...
OPENAI_API_KEY=...
OPENAI_BASE_URL=...
OPENAI_MODEL=...
FAST_MODEL=...
SMART_MODEL=...
VISION_MODEL=...
DATABASE_URL=sqlite+aiosqlite:////data/price.db
DATA_DIR=/data
PORT=8080
SERVE_HTTP=true
```

Не создавайте новую БД при обновлении существующего приложения.

## Health

```http
GET /health
```

Ожидаемый ответ:

```json
{
  "status": "ok",
  "app": "Clarify",
  "version": "0.3.0"
}
```

`GET /ready` отдельно показывает готовность БД, Telegram bot и scheduler.

## Тесты

```bash
python -m compileall -q app main.py
pytest -q
```

GitHub Actions выполняет:

1. install dependencies;
2. compileall;
3. полный pytest, включая legacy Pricebot тесты;
4. Docker build.

Платный внешний AI из тестов не вызывается.

## Production smoke-test

После deployment:

1. `/start`;
2. обычный текст;
3. Telegram Voice;
4. скриншот;
5. PDF;
6. `💰 Деньги`, `📅 Сроки`, `⚠️ Риски`;
7. follow-up: `а оплатить когда?`;
8. `👶 Просто`;
9. `🔀 Сравнить` два материала;
10. создать `📁 Проект`;
11. `/style` и «✍️ Написать»;
12. reminder;
13. `/ai_status`;
14. `/status` и `/ready`;
15. Telegram Stars PRO invoice.
