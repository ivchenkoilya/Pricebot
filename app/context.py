from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.ai.provider import OpenAICompatibleProvider
from app.config.settings import Settings
from app.database.session import Database
from app.processors.stt import build_stt
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
    projects: ProjectService
    styles: StyleService
    metrics: MetricService
    errors: ErrorService
    privacy: PrivacyService
    reminders: ReminderService
    subscriptions: SubscriptionService
    stt: object
    ai_sem: asyncio.Semaphore
    stt_sem: asyncio.Semaphore
    doc_sem: asyncio.Semaphore


def build_context(settings: Settings, db: Database, bot) -> AppContext:
    ai = OpenAICompatibleProvider(settings)
    materials = MaterialService(db, settings)
    return AppContext(
        settings=settings,
        db=db,
        ai=ai,
        bot=bot,
        users=UserService(db, settings),
        usage=UsageService(db, settings),
        materials=materials,
        projects=ProjectService(db),
        styles=StyleService(db),
        metrics=MetricService(db),
        errors=ErrorService(db),
        privacy=PrivacyService(db, materials),
        reminders=ReminderService(db),
        subscriptions=SubscriptionService(db),
        stt=build_stt(settings, ai),
        ai_sem=asyncio.Semaphore(settings.max_ai_concurrency),
        stt_sem=asyncio.Semaphore(settings.max_stt_concurrency),
        doc_sem=asyncio.Semaphore(settings.max_document_concurrency),
    )
