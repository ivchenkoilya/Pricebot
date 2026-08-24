from __future__ import annotations

from aiogram import Router

from app.bot.clarify_broadcast import build_broadcast_router
from app.bot.clarify_chat import build_chat_router
from app.bot.clarify_context import build_context_router
from app.bot.clarify_documents import build_document_router
from app.bot.clarify_growth import build_growth_router
from app.bot.clarify_image import build_image_router
from app.bot.clarify_media_links import build_media_links_router
from app.bot.clarify_menu import build_menu_router
from app.bot.clarify_precise_qa import build_precise_qa_router
from app.bot.clarify_prelaunch_menu import build_prelaunch_menu_router
from app.bot.clarify_referral_dismiss import build_referral_dismiss_router
from app.bot.clarify_start import build_start_router
from app.bot.clarify_stars import build_stars_router
from app.bot.clarify_support import build_support_router
from app.bot.clarify_video import build_video_router
from app.bot.clarify_voice import build_voice_router
from app.bot.clarify_web import build_web_router
from app.bot.razberi_general import build_general_router
from app.bot.razberi_materials import build_materials_router
from app.bot.razberi_media import build_media_router
from app.bot.razberi_payments_admin import build_payments_admin_router


def build_router(ctx) -> Router:
    router = Router(name='razberi')
    # Support is intentionally ahead of every generic/media route: while the
    # support FSM is active, user messages are transport and must never reach AI.
    router.include_router(build_start_router(ctx))
    router.include_router(build_growth_router(ctx))
    router.include_router(build_referral_dismiss_router(ctx))
    router.include_router(build_stars_router(ctx))
    router.include_router(build_support_router(ctx))
    router.include_router(build_broadcast_router(ctx))
    router.include_router(build_payments_admin_router(ctx))
    router.include_router(build_prelaunch_menu_router(ctx))
    router.include_router(build_menu_router(ctx))
    # Exact material questions use the improved retrieval/concise-answer path.
    router.include_router(build_precise_qa_router(ctx))
    router.include_router(build_materials_router(ctx))
    # Direct Telegram uploads remain supported. Public YouTube/media-link
    # extraction stays disabled until BOTH the feature flag and a real proxy are
    # configured, so an old Amvera MEDIA_DOWNLOAD_ENABLED=true cannot expose
    # broken download/subtitle buttons by itself.
    router.include_router(build_video_router(ctx))
    # Voice/audio goes through the dedicated multilingual handler before the
    # generic media router so the user sees transcription first, then analysis.
    router.include_router(build_voice_router(ctx))
    # Photos and image-documents use a bounded Vision fallback path before the
    # legacy generic media handler.
    router.include_router(build_image_router(ctx))
    # Text documents use one bounded AI analysis request after local extraction
    # and indexing. Image documents are intercepted by build_image_router above.
    router.include_router(build_document_router(ctx))
    router.include_router(build_media_router(ctx))
    media_links_ready = bool(ctx.settings.media_download_enabled and ctx.settings.media_proxy_url.strip())
    if media_links_ready:
        router.include_router(build_media_links_router(ctx))
    router.include_router(build_web_router(ctx))
    router.include_router(build_chat_router(ctx))
    router.include_router(build_context_router(ctx))
    router.include_router(build_general_router(ctx))
    return router
