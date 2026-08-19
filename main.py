from __future__ import annotations

import asyncio
import logging
import sys

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from fastapi import FastAPI

from app.bot.ai_handlers import create_ai_router
from app.bot.handlers import create_router
from app.bot.middlewares import UserRateLimitMiddleware
from app.config.settings import get_settings
from app.database.session import Database
from app.scheduler.runner import PriceScheduler
from app.services.ai import AIService
from app.trackers.registry import ProviderRegistry

settings = get_settings()
app = FastAPI(title='PRICE health', docs_url=None, redoc_url=None)


@app.get('/health')
async def health() -> dict[str, str]:
    return {'status': 'ok', 'app': settings.app_name, 'version': settings.version}


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        stream=sys.stdout,
    )


async def run_http() -> None:
    config = uvicorn.Config(app, host='0.0.0.0', port=settings.port, log_level='info')
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    configure_logging()
    log = logging.getLogger('price.main')
    if not settings.bot_token:
        raise RuntimeError('BOT_TOKEN is required. Add it as an environment variable; never commit it to GitHub.')

    db = Database(settings)
    await db.init()
    registry = ProviderRegistry(settings)
    ai = AIService(settings)
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    scheduler = PriceScheduler(db, registry, bot, settings)
    dp = Dispatcher(storage=MemoryStorage())
    limiter = UserRateLimitMiddleware(settings.user_rate_limit_per_minute)
    dp.message.middleware(limiter)
    dp.callback_query.middleware(limiter)

    # AI router is deliberately before the core router, but it only handles
    # ordinary non-URL text while no FSM dialog is active. Price URLs and
    # target-price dialogs therefore keep deterministic non-AI behavior.
    dp.include_router(create_ai_router(ai))
    dp.include_router(create_router(settings, db, registry, scheduler))

    tasks = [
        asyncio.create_task(dp.start_polling(bot), name='telegram'),
        asyncio.create_task(scheduler.loop(), name='scheduler'),
    ]
    if settings.serve_http:
        tasks.append(asyncio.create_task(run_http(), name='http'))
    log.info('PRICE %s starting ai=%s model=%s', settings.version, 'on' if ai.enabled else 'off', settings.openai_model)
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await ai.close()
        await bot.session.close()
        await db.close()
        log.info('PRICE stopped')


if __name__ == '__main__':
    asyncio.run(main())
