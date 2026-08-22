from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.bot.razberi_handlers import build_router
from app.bot.razberi_middlewares import RateLimitMiddleware
from app.brand import clarify_banner_jpeg, clarify_banner_webp
from app.config.settings import get_settings
from app.context import build_context
from app.database.session import Database
from app.webapp import webapp_api_router

settings = get_settings()
app = FastAPI(title='Clarify', version=settings.version, docs_url=None, redoc_url=None)
app.state.settings = settings
app.state.ctx = None
app.include_router(webapp_api_router)

if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=['GET', 'POST', 'PATCH', 'DELETE', 'OPTIONS'],
        allow_headers=['Authorization', 'Content-Type', 'X-Telegram-Init-Data'],
    )


@app.middleware('http')
async def prevent_stale_webapp_shell(request: Request, call_next):
    """Do not let Telegram Android keep an old SPA index after redeploys.

    Hashed JS/CSS assets may be cached safely, but a cached index.html can point
    at assets from a previous Amvera image and produce the blank blue WebView
    seen when opening Clarify from a persistent reply-keyboard button.
    """
    response = await call_next(request)
    path = request.url.path.rstrip('/')
    if path in {'/app', '/app/index.html'}:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


ROOT = Path(__file__).resolve().parent
WEBAPP_DIST = ROOT / 'webapp' / 'dist'
app.mount('/app', StaticFiles(directory=str(WEBAPP_DIST), html=True, check_dir=False), name='webapp')

_runtime_db: Database | None = None
_scheduler_running = False
_bot_initialized = False


@app.get('/')
async def root():
    return RedirectResponse('/app/')


@app.get('/assets/clarify-banner.webp')
async def clarify_banner_webp_route():
    return Response(
        content=clarify_banner_webp(),
        media_type='image/webp',
        headers={'Cache-Control': 'public, max-age=120, must-revalidate'},
    )


@app.get('/assets/clarify-banner.jpg')
async def clarify_banner_jpeg_route():
    return Response(
        content=clarify_banner_jpeg(),
        media_type='image/jpeg',
        headers={'Cache-Control': 'public, max-age=120, must-revalidate'},
    )


@app.get('/health')
async def health() -> dict[str, str]:
    return {'status': 'ok', 'app': settings.app_name, 'version': settings.version}


@app.get('/ready')
async def ready() -> dict[str, object]:
    db_ok = bool(_runtime_db and await _runtime_db.ping())
    ok = db_ok and _bot_initialized and _scheduler_running
    return {
        'status': 'ready' if ok else 'not_ready',
        'database': db_ok,
        'bot_initialized': _bot_initialized,
        'scheduler': _scheduler_running,
        'webapp_build': (WEBAPP_DIST / 'index.html').exists(),
    }


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        stream=sys.stdout,
    )


async def run_http() -> None:
    server = uvicorn.Server(uvicorn.Config(app, host='0.0.0.0', port=settings.port, log_level='info'))
    await server.serve()


async def main() -> None:
    global _runtime_db, _scheduler_running, _bot_initialized

    configure_logging()
    log = logging.getLogger('clarify.main')
    settings.ensure_dirs()
    if not settings.bot_token:
        raise RuntimeError('BOT_TOKEN is required. Add it as an environment variable; never commit it to GitHub.')

    db = Database(settings)
    _runtime_db = db
    await db.init()

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    _bot_initialized = True
    try:
        await bot.set_my_commands([
            BotCommand(command='start', description='Начать работу'),
            BotCommand(command='help', description='Помощь'),
            BotCommand(command='about', description='О Clarify'),
            BotCommand(command='examples', description='Примеры запросов'),
            BotCommand(command='summary', description='Кратко о последнем материале'),
            BotCommand(command='clear', description='Очистить контекст'),
            BotCommand(command='stars', description='Баланс Stars (владелец)'),
        ])
    except Exception as exc:
        log.warning('Could not configure Telegram command menu: %s', exc)

    ctx = build_context(settings, db, bot)
    app.state.ctx = ctx

    dispatcher = Dispatcher(storage=MemoryStorage())
    limiter = RateLimitMiddleware(settings.requests_per_minute, settings.max_active_jobs_per_user)
    dispatcher.message.outer_middleware(limiter)
    dispatcher.callback_query.outer_middleware(limiter)
    dispatcher.include_router(build_router(ctx))

    scheduler = AsyncIOScheduler(timezone='UTC')

    async def send_due_reminders() -> None:
        for reminder, telegram_id in await ctx.reminders.due():
            try:
                await bot.send_message(telegram_id, f'⏰ <b>Напоминание</b>\n\n{reminder.text}')
            except Exception as exc:
                await ctx.errors.record(f'reminder-{reminder.id}', telegram_id, 'reminder_send', exc)

    async def prewarm_stt() -> None:
        provider = (settings.stt_provider or 'local').strip().lower()
        try:
            await ctx.stt.prewarm()
            if provider == 'yandex':
                log.info(
                    'STT ready provider=yandex speechkit_key=%s folder_id=%s fallback_local=%s',
                    'set' if settings.yandex_speechkit_api_key.strip() else 'missing',
                    'set' if settings.yandex_speechkit_folder_id.strip() else 'missing',
                    settings.yandex_speechkit_fallback_local,
                )
            else:
                log.info(
                    'STT ready provider=%s model=%s workers=%s chunks=%s',
                    provider,
                    settings.whisper_model,
                    settings.whisper_num_workers,
                    settings.whisper_parallel_chunks,
                )
        except Exception as exc:
            log.warning('STT prewarm failed provider=%s: %s', provider, exc)

    scheduler.add_job(send_due_reminders, 'interval', seconds=20, max_instances=1, coalesce=True)
    scheduler.add_job(ctx.materials.cleanup_expired, 'cron', hour=4, minute=10, max_instances=1, coalesce=True)
    scheduler.start()
    _scheduler_running = True

    tasks = [
        asyncio.create_task(
            dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types()),
            name='telegram',
        ),
        asyncio.create_task(prewarm_stt(), name='stt-prewarm'),
    ]
    if settings.serve_http:
        tasks.append(asyncio.create_task(run_http(), name='http'))

    log.info(
        'Clarify %s starting ai=%s endpoint=%s fast=%s smart=%s stt=%s whisper=%s webapp=%s',
        settings.version,
        'on' if settings.ai_available else 'off',
        ctx.ai.endpoint_label,
        settings.fast,
        settings.smart,
        settings.stt_provider,
        settings.whisper_model,
        settings.webapp_url or '/app/',
    )
    try:
        await asyncio.gather(*tasks)
    finally:
        _scheduler_running = False
        scheduler.shutdown(wait=False)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await ctx.ai.close()
        await bot.session.close()
        await db.close()
        app.state.ctx = None
        _runtime_db = None
        _bot_initialized = False
        log.info('Clarify stopped')


if __name__ == '__main__':
    asyncio.run(main())
