# Clarify 0.5.0 — COPILOT

**Send anything. Get clarity.**

Clarify — Telegram AI-помощник для текста, голосовых, документов, изображений, ссылок и переписки. Он не просто делает выжимку: Clarify запоминает рабочий контекст, отвечает на уточнения и помогает понять, что делать дальше.

Проект является продолжением существующего `Pricebot`. Сохраняются GitHub/Amvera-инфраструктура, `/data/price.db`, пользователи, PRO-состояния, Stars-платежи и legacy-модули Pricebot.

## Главное в 0.5 COPILOT

### 🔗 Ссылки

Можно отправить обычный URL:

```text
https://example.com/article
```

Clarify прочитает публичную страницу и сделает разбор.

Можно сразу задать задачу:

```text
https://example.com/article что здесь главное?
```

Тогда бот отвечает именно на вопрос и сохраняет страницу как материал для дальнейшего диалога.

Чтение использует существующий безопасный `PageReader`: direct HTML → Jina Reader fallback → публичный URL fallback. Login, CAPTCHA и access-control не обходятся.

### 🧠 Контекст нескольких материалов

Clarify больше не привязан только к последнему файлу. Он выбирает небольшой рабочий набор из недавних материалов по смыслу и ссылкам вроде:

```text
а оплатить когда?
а что было во втором?
что там было про гарантию?
а если задержат?
```

Например, если подряд отправить фото, договор и голосовое, вопрос про гарантию может вернуться к договору, а не к самому последнему материалу.

### 📸 Фото + подпись

Подпись становится задачей для vision-модели:

```text
[фото] что у него на голове?
[скрин] что здесь не так?
```

Clarify сначала отвечает на вопрос, а не выдаёт универсальный шаблон разбора.

### 📄 Документ + подпись

То же работает с PDF/DOCX/TXT/XLSX/CSV:

```text
[PDF] когда нужно оплатить?
[договор] какие здесь риски?
```

Если PDF содержит маркеры страниц, ответ должен указывать страницу для ключевого факта.

### 📚 Источники и страницы

PDF извлекается с маркерами:

```text
[Страница 7]
...
```

При chunking номер текущей страницы переносится в кусок даже если разрез произошёл посередине страницы. Q&A получает инструкцию не придумывать номер страницы и ссылаться только на маркеры, реально присутствующие в retrieved-контексте.

### ⚡ Короткие карточки

Фото и голосовые теперь показывают прямой вывод первым. Большие блоки `Коротко / Главное / ...` не выводятся автоматически, если можно ответить компактнее.

### 👁 Vision без уверенных догадок

Если визуальную деталь нельзя определить уверенно, модель должна прямо сообщить неопределённость. Уточняющие вопросы по недавно отправленному фото повторно открывают сохранённый Telegram `file_id` и смотрят исходное изображение.

## Что умеет Clarify

- текст и длинные сообщения;
- Telegram Voice и аудиофайлы;
- PDF, DOCX, TXT, Markdown, XLSX, CSV;
- JPG, JPEG, PNG, WEBP;
- публичные веб-ссылки;
- пересланные Telegram-сообщения;
- вопросы по ранее отправленным материалам;
- сравнение двух материалов;
- проекты/папки;
- напоминания;
- «Напиши за меня» с пользовательским стилем;
- FREE/PRO и Telegram Stars.

## Главное меню

- 📎 Разобрать
- ✍️ Написать
- 🧠 Мои материалы
- 🔀 Сравнить
- 📁 Проекты
- 👑 PRO
- ⚙️ Настройки
- ❓ Помощь

Меню необязательно: материал можно просто отправить в чат.

## Архитектура

```text
main.py
app/
  ai/
    conversation.py       # multi-material context + URL parsing
    context.py            # visual follow-ups
    intent.py             # local intent router
    provider.py           # OpenAI-compatible text/vision
    schemas.py
  bot/
    clarify_web.py        # public web links
    clarify_context.py    # visual + conversation follow-ups
    razberi_handlers.py   # router aggregator; legacy filename kept
    razberi_general.py
    razberi_materials.py
    razberi_media.py
    razberi_payments_admin.py
  config/settings.py
  database/
    models.py             # legacy Pricebot tables
    razberi_models.py     # additive Clarify tables
    session.py
  processors/
    common.py             # chunks, retrieval, page-marker propagation
    documents.py
    stt.py
    text.py
  services/
    core.py
    page_reader.py
    reminders.py
    subscriptions.py
```

## База данных и совместимость

На Amvera используется тот же persistent-файл:

```env
DATABASE_URL=sqlite+aiosqlite:////data/price.db
DATA_DIR=/data
```

Clarify 0.5 не требует миграции схемы. Существующие пользователи, PRO, платежи, материалы, проекты и legacy Pricebot-таблицы сохраняются.

## AI

Минимально:

```env
AI_ENABLED=true
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://ваш-openai-compatible-endpoint/v1
OPENAI_MODEL=...
FAST_MODEL=...
SMART_MODEL=...
VISION_MODEL=...
```

Fallback:

- пустой `FAST_MODEL` → `OPENAI_MODEL`;
- пустой `SMART_MODEL` → `OPENAI_MODEL`;
- пустой `VISION_MODEL` → `SMART_MODEL`, затем `OPENAI_MODEL`.

Проверка:

```text
/ai_status
```

## Скорость

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

Большие документы используют parallel map/reduce. Скриншоты уменьшаются перед vision. Обычные follow-up используют fast-модель, если deep-анализ не требуется.

## Голосовые

Local:

```env
STT_PROVIDER=local
WHISPER_MODEL=base
WHISPER_COMPUTE_TYPE=int8
```

Remote, если OpenAI-compatible endpoint поддерживает transcriptions:

```env
STT_PROVIDER=remote
STT_REMOTE_MODEL=whisper-1
STT_REMOTE_TIMEOUT=25
```

Локальная модель кэшируется в persistent `/data/whisper-cache`.

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

PRO не является техническим безлимитом: production-лимиты остаются для защиты сервиса.

## Telegram Stars

`👑 PRO` создаёт invoice в `XTR`. Успешная оплата записывается в БД и активирует PRO. Состояние не хранится только в памяти и переживает restart.

## Безопасность

- `BOT_TOKEN` и API keys только через environment variables;
- содержимое пользовательских материалов считается untrusted input;
- команды внутри сайта, документа, картинки или пересланного сообщения не становятся system-инструкциями;
- публичный PageReader не обходит CAPTCHA/login/access controls;
- URL проверяется существующим SSRF-safe валидатором;
- исполняемые файлы не принимаются;
- временные файлы удаляются;
- traceback пользователю не показывается;
- `/delete_my_data` удаляет пользовательские материалы/контекст, но оставляет финансовые записи для корректного учёта.

## Amvera

В репозитории уже есть `Dockerfile` и `amvera.yaml` с persistent mount `/data` и портом `8080`.

Минимальные переменные:

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
```

После deploy:

1. `GET /health` → `Clarify 0.5.0`;
2. `GET /ready` → database/bot/scheduler ready;
3. `/ai_status` в Telegram;
4. фото + подпись;
5. уточнение по фото;
6. PDF + вопрос;
7. URL + вопрос;
8. несколько материалов + follow-up;
9. PRO/Stars smoke-test.

## Тесты

```bash
python -m compileall -q app main.py
pytest -q
```

GitHub Actions выполняет:

1. установку зависимостей;
2. compileall;
3. весь pytest;
4. production Docker build.

Внешний платный AI в автоматических тестах не вызывается.
