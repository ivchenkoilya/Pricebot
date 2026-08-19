from __future__ import annotations

from aiogram import Router

from app.bot.clarify_context import build_context_router
from app.bot.razberi_general import build_general_router
from app.bot.razberi_materials import build_materials_router
from app.bot.razberi_media import build_media_router
from app.bot.razberi_payments_admin import build_payments_admin_router


def build_router(ctx) -> Router:
    router = Router(name='razberi')
    # Specific routes first. Context follow-ups must run before the final general
    # catch-all text handler so an image question can re-open the original photo.
    router.include_router(build_payments_admin_router(ctx))
    router.include_router(build_materials_router(ctx))
    router.include_router(build_media_router(ctx))
    router.include_router(build_context_router(ctx))
    router.include_router(build_general_router(ctx))
    return router
