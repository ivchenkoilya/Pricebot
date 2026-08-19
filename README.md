# РАЗБЕРИ 0.1.0

**Скинь что угодно. Я разберусь.**

Этот репозиторий — не новый проект с нуля. **RAZBERI 0.1.0 построен как обновление существующего Pricebot**: сохраняются текущая GitHub/Amvera-инфраструктура, таблица пользователей, действующий `price.db`, OpenAI-compatible подключение и legacy-модули мониторинга цен. Новый пользовательский интерфейс и новые таблицы RAZBERI добавляются поверх существующей базы без destructive migration.

## Что умеет бот

- обычный и длинный текст: краткое содержание, главное, задачи, даты, суммы, предупреждения;
- Telegram Voice и аудиофайлы через локальный `faster-whisper` или OpenAI-compatible STT;
- PDF, DOCX, TXT, Markdown, XLSX и CSV;
- изображения и скриншоты через `VISION_MODEL`;
- OCR/vision для PDF только когда нормальный text layer отсутствует;
- вопросы по ранее загруженному материалу через chunks + retrieval;
- «Напиши за меня» и варианты ответа на пересланное сообщение;
- напоминания, переживающие restart;
- FREE/PRO лимиты;
- Telegram Stars с 30-дневной подпиской;
- `/ai_status`, `/status`, `/admin`, `/test`, `/delete_my_data`;
- FastAPI `/health` и `/ready`;
- Docker + Amvera + GitHub Actions.

## Главное меню

- 📎 Разобрать
- 🎤 Голосовые
- 📄 Документы
- ✍️ Написать
- 🧠 Мои материалы
- 👑 PRO
- ⚙️ Настройки
- ❓ Помощь

Меню не обязательно: текст, voice, фото и документы можно просто отправлять в чат.

## Архитектура

```text
main.py
app/
  ai/
    provider.py
    schemas.py
  bot/
    razberi_handlers.py       # агрегатор routers
    razberi_general.py
    razberi_materials.py
    razberi_media.py
    razberi_payments_admin.py
    razberi_helpers.py
    razberi_keyboards.py
    razberi_middlewares.py
    razberi_states.py
  config/
    settings.py
  database/
    models.py              # существующие Pricebot таблицы
    razberi_models.py      # новые additive-таблицы RAZBERI
    session.py
  processors/
    common.py
    documents.py
    router.py
    stt.py
    text.py
  services/
    core.py
    reminders.py
    subscriptions.py
  trackers/                # legacy Pricebot сохранён
  payments/                # legacy Pricebot сохранён
```

### Совместимость с Pricebot

По умолчанию Amvera продолжает использовать:

```env
DATABASE_URL=sqlite+aiosqlite:////data/price.db
```

Это намеренно: существующие `users`, старые подписки и price-tracker данные не теряются. Новые сущности используют таблицы с префиксом `razberi_`. Старые `products`, `watches`, `price_history`, provider-код и тесты остаются в репозитории, чтобы обновление было обратимым и история проекта не исчезала.

## SmartAPI / OpenAI-compatible API

RAZBERI не хардкодит адрес OpenAI. В Amvera или `.env` задайте:

```env
AI_ENABLED=true
OPENAI_API_KEY=ваш_ключ
OPENAI_BASE_URL=https://ваш-openai-compatible-endpoint/v1
OPENAI_MODEL=имя_модели
FAST_MODEL=
SMART_MODEL=
VISION_MODEL=
```

Если `FAST_MODEL`, `SMART_MODEL` или `VISION_MODEL` пусты, используется `OPENAI_MODEL`.

Проверка реального подключения:

```text
/ai_status
```

Команда делает настоящий короткий API-запрос и не показывает ключ.

## Speech-to-Text

Локальный вариант без отдельного платного STT API:

```env
STT_PROVIDER=local
WHISPER_MODEL=base
WHISPER_COMPUTE_TYPE=int8
```

Модель загружается лениво и кэшируется. В Docker кэш лежит в `/data/whisper-cache`, поэтому на Amvera он переживает restart/redeploy при сохранённом persistent volume.

Если ваш OpenAI-compatible gateway поддерживает `/audio/transcriptions`:

```env
STT_PROVIDER=smartapi
```

## Документы

Поддерживаются:

- `.pdf`
- `.docx`
- `.txt`
- `.md`
- `.xlsx`
- `.csv`
- `.jpg`, `.jpeg`, `.png`, `.webp` как vision input

PDF сначала читается через PyMuPDF. Рендер страниц и vision/OCR используется только если извлечённого текста практически нет.

Большие тексты режутся на chunks и обрабатываются map-reduce, а вопросы по материалам получают только релевантные chunks вместо повторной отправки всего документа.

## FREE / PRO

Базовые значения полностью вынесены в env:

```env
FREE_DAILY_AI_LIMIT=10
PRO_DAILY_AI_LIMIT=150
FREE_VOICE_DAILY_LIMIT=3
FREE_VOICE_MAX_SECONDS=120
FREE_DOCUMENT_MAX_PAGES=10
PRO_DOCUMENT_MAX_PAGES=200
PRO_STARS_PRICE=299
```

PRO не называется «безлимитом»: у него остаются разумные production-ограничения.

## Telegram Stars

Кнопка `👑 PRO` создаёт invoice link в валюте `XTR`. Успешный `successful_payment` записывается в БД и активирует PRO. Подписка и финансовая запись не хранятся только в памяти, поэтому restart их не сбрасывает.

Администратор также имеет служебные механизмы отмены/возврата, если они поддерживаются текущей Telegram Bot API версией и правами бота.

## Напоминания

Примеры:

```text
напомни завтра оплатить поставщика
напомни через два часа позвонить
напомни в пятницу проверить заказ
```

После распознавания бот показывает подтверждение. После нажатия «✅ Создать» напоминание становится активным, сохраняется в SQLite, а scheduler регулярно отправляет наступившие active-записи. Поэтому restart не удаляет задачу.

## Приватность и безопасность

- API keys и `BOT_TOKEN` только через environment variables;
- содержимое документов/голосовых не пишется в обычный лог;
- пользовательские файлы не исполняются;
- есть whitelist расширений и лимит размера;
- пользовательское имя файла не используется как filesystem path;
- документы, изображения, сайты и пересланные сообщения считаются недоверенными данными, а не system instructions;
- `/delete_my_data` удаляет материалы, chunks, reminders и связанную AI-историю, но не уничтожает финансовые записи, нужные для платежного учёта;
- временные файлы удаляются после обработки;
- ошибки пользователю показываются без traceback.

## Локальный запуск

Требуется Python 3.12+ и `ffmpeg`.

```bash
python -m venv .venv
```

Linux/macOS:

```bash
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python main.py
```

Минимально заполните:

```env
BOT_TOKEN=
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=
```

## Amvera

В репозитории уже есть `amvera.yaml` и `Dockerfile`. `amvera.yaml` монтирует persistent storage в `/data`, а контейнер слушает `8080`.

Минимальные переменные Amvera:

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

### Развёртывание на Amvera с Android

1. Откройте репозиторий GitHub и убедитесь, что нужная ветка/PR уже в `main`.
2. В Amvera создайте или откройте существующее Docker-приложение Pricebot.
3. Не создавайте новый проект/новую БД: используйте тот же persistent `/data`.
4. Добавьте новые переменные из `.env.example`. Реальные ключи не коммитьте в GitHub.
5. Запустите deployment.
6. Откройте `https://ВАШ-ДОМЕН/health` — ожидается `RAZBERI 0.1.0`.
7. Откройте `/ready` — БД, бот и scheduler должны быть ready.
8. В Telegram вызовите `/ai_status`.
9. Затем проверьте по очереди: текст → voice → PDF → вопрос по PDF → reminder → PRO.

## Health

```http
GET /health
```

```json
{
  "status": "ok",
  "app": "RAZBERI",
  "version": "0.1.0"
}
```

`GET /ready` дополнительно показывает готовность БД, Telegram bot и scheduler без раскрытия секретов.

## Тесты

```bash
python -m compileall -q app main.py
pytest -q
```

GitHub Actions выполняет:

1. установку зависимостей;
2. compileall;
3. pytest;
4. Docker build.

Внешний платный AI в автоматических тестах не вызывается.

## Быстрый production smoke-test

После деплоя:

1. `/start`;
2. отправить обычный текст;
3. отправить Telegram Voice;
4. открыть полную расшифровку/действия;
5. отправить PDF;
6. нажать `❓ Спросить` и задать вопрос только по документу;
7. написать «напомни через 10 минут проверить заказ»;
8. `/ai_status`;
9. открыть `👑 PRO` и проверить Stars invoice;
10. `/status` и `/ready`.

Если AI-провайдер не поддерживает vision или STT endpoint, соответствующая функция должна сообщить об ограничении, а не уронить весь bot process.
