from __future__ import annotations

from aiogram import Router

from app.bot.clarify_context import build_context_router
from app.bot.clarify_start import build_start_router
from app.bot.clarify_web import build_web_router
from app.bot.razberi_general import build_general_router
from app.bot.razberi_materials import build_materials_router
from app.bot.razberi_media import build_media_router
from app.bot.razberi_payments_admin import build_payments_admin_router


def build_router(ctx) -> Router:
    router = Router(name='razberi')
    # Specific routes first. The branded /start handler intentionally runs before
    # the legacy general router so the old start handler remains a safe fallback.
    router.include_router(build_start_router(ctx))
    router.include_router(build_payments_admin_router(ctx))
    router.include_router(build_materials_router(ctx))
    router.include_router(build_media_router(ctx))
    router.include_router(build_web_router(ctx))
    router.include_router(build_context_router(ctx))
    router.include_router(build_general_router(ctx))
    return router
