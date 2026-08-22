from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.ai.provider import OpenAICompatibleProvider
from app.config.settings import Settings
from app.database.session import Database
from app.processors.stt import build_stt
from app.processors.yandex_stt import YandexSpeechKitProvider
from app.services.conversation_context import ConversationContextService
from app.services.core import (
    ErrorService,
    MaterialService,
    MetricService,
    PrivacyService,
    ProjectService,
    StyleService,
    UsageService,
    UserService,
)
from app.services.fast_media import FastMediaDownloader
from app.services.growth import GrowthService
from app.services.media_downloader import MediaDownloader
from app.services.page_reader import PageReader
from app.services.reminders import ReminderService
from app.services.subscriptions import SubscriptionService


@dataclass(slots=True)
class AppContext:
    settings: Settings
    db: Database
    ai: OpenAICompatibleProvider
    bot: object
    users: UserService
    usage: UsageService
    materials: MaterialService
    conversations: ConversationContextService
    projects: ProjectService
    styles: StyleService
    metrics: MetricService
    errors: ErrorService
    privacy: PrivacyService
    reminders: ReminderService
    subscriptions: SubscriptionService
    growth: GrowthService
    page_reader: PageReader
    media_downloader: MediaDownloader
    stt: object
    media_stt: object
    ai_sem: asyncio.Semaphore
    stt_sem: asyncio.Semaphore
    doc_sem: asyncio.Semaphore


def _build_primary_stt(settings: Settings, ai):
    provider = (settings.stt_provider or 'local').strip().lower()
    # build_stt intentionally remains the source of the local/OpenAI provider.
    # When Yandex is selected we wrap a lazy local provider as a safety fallback.
    base = build_stt(settings.model_copy(update={'stt_provider': 'local'}) if provider == 'yandex' else settings, ai)
    if provider == 'yandex':
        return YandexSpeechKitProvider(settings, fallback=base)
    return base


def build_context(settings: Settings, db: Database, bot) -> AppContext:
    ai = OpenAICompatibleProvider(settings)
    materials = MaterialService(db, settings)
    conversations = ConversationContextService(db, materials, settings)
    media_stt_settings = settings.model_copy(update={'whisper_model': settings.media_whisper_model})
    return AppContext(
        settings=settings,
        db=db,
        ai=ai,
        bot=bot,
        users=UserService(db, settings),
        usage=UsageService(db, settings),
        materials=materials,
        conversations=conversations,
        projects=ProjectService(db),
        styles=StyleService(db),
        metrics=MetricService(db),
        errors=ErrorService(db),
        privacy=PrivacyService(db, materials),
        reminders=ReminderService(db),
        subscriptions=SubscriptionService(db),
        growth=GrowthService(db, settings),
        page_reader=PageReader(settings),
        media_downloader=FastMediaDownloader(settings),
        stt=_build_primary_stt(settings, ai),
        media_stt=_build_primary_stt(media_stt_settings, ai),
        ai_sem=asyncio.Semaphore(settings.max_ai_concurrency),
        stt_sem=asyncio.Semaphore(settings.max_stt_concurrency),
        doc_sem=asyncio.Semaphore(settings.max_document_concurrency),
    )
