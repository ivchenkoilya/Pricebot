from __future__ import annotations

from aiogram import Router

from app.bot.razberi_general import build_general_router
from app.bot.razberi_materials import build_materials_router
from app.bot.razberi_media import build_media_router
from app.bot.razberi_payments_admin import build_payments_admin_router


def build_router(ctx) -> Router:
    router = Router(name='razberi')
    # Specific routes first. General router contains the final catch-all text handler.
    router.include_router(build_payments_admin_router(ctx))
    router.include_router(build_materials_router(ctx))
    router.include_router(build_media_router(ctx))
    router.include_router(build_general_router(ctx))
    return router
