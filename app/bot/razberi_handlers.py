from __future__ import annotations

from aiogram import Router

from app.bot.clarify_chat import build_chat_router
from app.bot.clarify_context import build_context_router
from app.bot.clarify_growth import build_growth_router
from app.bot.clarify_media_links import build_media_links_router
from app.bot.clarify_menu import build_menu_router
from app.bot.clarify_start import build_start_router
from app.bot.clarify_stars import build_stars_router
from app.bot.clarify_support import build_support_router
from app.bot.clarify_video import build_video_router
from app.bot.clarify_web import build_web_router
from app.bot.razberi_general import build_general_router
from app.bot.razberi_materials import build_materials_router
from app.bot.razberi_media import build_media_router
from app.bot.razberi_payments_admin import build_payments_admin_router


def build_router(ctx) -> Router:
    router = Router(name='razberi')
    # Specific routes first. Persistent menu actions are intentionally before
    # generic text/context routers so buttons never become ordinary materials.
    router.include_router(build_start_router(ctx))
    router.include_router(build_growth_router(ctx))
    router.include_router(build_stars_router(ctx))
    router.include_router(build_support_router(ctx))
    router.include_router(build_payments_admin_router(ctx))
    router.include_router(build_menu_router(ctx))
    router.include_router(build_materials_router(ctx))
    router.include_router(build_video_router(ctx))
    router.include_router(build_media_router(ctx))
    router.include_router(build_media_links_router(ctx))
    router.include_router(build_web_router(ctx))
    router.include_router(build_chat_router(ctx))
    router.include_router(build_context_router(ctx))
    router.include_router(build_general_router(ctx))
    return router
