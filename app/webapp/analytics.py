from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, func, select
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models import Base, User
from app.database.razberi_models import ErrorLog, RazberiPayment, Referral, UserAcquisition
from app.services.core import is_creator
from app.webapp.auth import TelegramWebAppUser, runtime_context, telegram_webapp_user

router = APIRouter(prefix='/api/analytics', tags=['clarify-analytics'])

ALLOWED_EVENTS = {
    'open_mini_app', 'demo_open', 'material_upload_started', 'material_upload_success',
    'analysis_started', 'analysis_success', 'analysis_failed', 'ask_material_question',
    'write_generate', 'tariffs_open', 'payment_started', 'payment_success', 'invite_open',
    'referral_shared', 'return_day_1', 'return_day_7',
}


class AnalyticsEvent(Base):
    """Privacy-safe product funnel event. Source material content is never stored."""

    __tablename__ = 'clarify_analytics_events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(64), default='direct', index=True)
    campaign: Mapped[str | None] = mapped_column(String(128), index=True)
    material_type: Mapped[str | None] = mapped_column(String(32), index=True)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer)
    error_type: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class EventBody(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    material_type: str | None = Field(default=None, max_length=32)
    processing_time_ms: int | None = Field(default=None, ge=0, le=7_200_000)
    error_type: str | None = Field(default=None, max_length=64)


def _tg_namespace(tg: TelegramWebAppUser):
    return SimpleNamespace(id=tg.id, username=tg.username, first_name=tg.first_name or 'User')


def _clean(value: str | None, limit: int) -> str | None:
    clean = ''.join(ch for ch in (value or '').strip().lower() if ch.isalnum() or ch in {'_', '-', '.'})[:limit]
    return clean or None


async def _record_retention(db, user_id: int, acquisition: UserAcquisition | None, now: datetime) -> None:
    if acquisition is None or acquisition.first_seen_at is None:
        return
    age = now - acquisition.first_seen_at
    names: list[str] = []
    if age >= timedelta(days=1):
        names.append('return_day_1')
    if age >= timedelta(days=7):
        names.append('return_day_7')
    for name in names:
        exists = (await db.execute(
            select(AnalyticsEvent.id).where(
                AnalyticsEvent.user_id == user_id,
                AnalyticsEvent.name == name,
            ).limit(1)
        )).scalar_one_or_none()
        if exists is None:
            db.add(AnalyticsEvent(
                user_id=user_id,
                name=name,
                source=acquisition.source or 'direct',
                campaign=acquisition.campaign,
            ))


@router.post('/event')
async def analytics_event(
    body: EventBody,
    request: Request,
    tg: TelegramWebAppUser = Depends(telegram_webapp_user),
):
    if body.name not in ALLOWED_EVENTS:
        raise HTTPException(400, 'Неизвестное событие аналитики')
    ctx = runtime_context(request)
    user = await ctx.users.upsert(_tg_namespace(tg))
    now = datetime.utcnow()
    async with ctx.db.sessions() as db:
        acquisition = (await db.execute(
            select(UserAcquisition).where(UserAcquisition.user_id == user.id)
        )).scalar_one_or_none()
        db.add(AnalyticsEvent(
            user_id=user.id,
            name=body.name,
            source=(acquisition.source if acquisition else 'direct') or 'direct',
            campaign=acquisition.campaign if acquisition else None,
            material_type=_clean(body.material_type, 32),
            processing_time_ms=body.processing_time_ms,
            error_type=_clean(body.error_type, 64),
            created_at=now,
        ))
        if body.name == 'open_mini_app':
            await _record_retention(db, user.id, acquisition, now)
        await db.commit()
    return {'ok': True}


@router.get('/admin/overview')
async def analytics_admin_overview(
    request: Request,
    tg: TelegramWebAppUser = Depends(telegram_webapp_user),
):
    ctx = runtime_context(request)
    user = await ctx.users.upsert(_tg_namespace(tg))
    if not is_creator(user, ctx.settings):
        raise HTTPException(403, 'Доступно только администратору')

    now = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = now - timedelta(days=7)
    month = now - timedelta(days=30)
    async with ctx.db.sessions() as db:
        users_total = int((await db.execute(select(func.count(User.id)))).scalar_one() or 0)
        new_today = int((await db.execute(select(func.count(UserAcquisition.id)).where(UserAcquisition.first_seen_at >= today))).scalar_one() or 0)
        new_7d = int((await db.execute(select(func.count(UserAcquisition.id)).where(UserAcquisition.first_seen_at >= week))).scalar_one() or 0)
        registrations = int((await db.execute(select(func.count(UserAcquisition.id)))).scalar_one() or 0)
        first_analyses = int((await db.execute(select(func.count(UserAcquisition.id)).where(UserAcquisition.first_analysis_at.is_not(None)))).scalar_one() or 0)
        mini_app_opens = int((await db.execute(select(func.count(AnalyticsEvent.id)).where(AnalyticsEvent.name == 'open_mini_app', AnalyticsEvent.created_at >= week))).scalar_one() or 0)
        success_7d = int((await db.execute(select(func.count(AnalyticsEvent.id)).where(AnalyticsEvent.name == 'analysis_success', AnalyticsEvent.created_at >= week))).scalar_one() or 0)
        failed_7d = int((await db.execute(select(func.count(AnalyticsEvent.id)).where(AnalyticsEvent.name == 'analysis_failed', AnalyticsEvent.created_at >= week))).scalar_one() or 0)
        avg_processing = int((await db.execute(select(func.coalesce(func.avg(AnalyticsEvent.processing_time_ms), 0)).where(
            AnalyticsEvent.name.in_(['material_upload_success', 'analysis_success']),
            AnalyticsEvent.processing_time_ms.is_not(None),
            AnalyticsEvent.created_at >= week,
        ))).scalar_one() or 0)
        payment_started = int((await db.execute(select(func.count(AnalyticsEvent.id)).where(AnalyticsEvent.name == 'payment_started', AnalyticsEvent.created_at >= week))).scalar_one() or 0)
        payment_success = int((await db.execute(select(func.count(AnalyticsEvent.id)).where(AnalyticsEvent.name == 'payment_success', AnalyticsEvent.created_at >= week))).scalar_one() or 0)
        stars_30d = int((await db.execute(select(func.coalesce(func.sum(RazberiPayment.amount), 0)).where(
            RazberiPayment.created_at >= month,
            RazberiPayment.status == 'paid',
            RazberiPayment.currency == 'XTR',
        ))).scalar_one() or 0)
        errors_7d = int((await db.execute(select(func.count(ErrorLog.id)).where(ErrorLog.created_at >= week))).scalar_one() or 0)
        referral_invited = int((await db.execute(select(func.count(Referral.id)))).scalar_one() or 0)
        referral_activated = int((await db.execute(select(func.count(Referral.id)).where(Referral.status == 'rewarded'))).scalar_one() or 0)
        type_rows = (await db.execute(
            select(AnalyticsEvent.material_type, func.count(AnalyticsEvent.id))
            .where(AnalyticsEvent.name == 'analysis_success', AnalyticsEvent.material_type.is_not(None), AnalyticsEvent.created_at >= week)
            .group_by(AnalyticsEvent.material_type)
            .order_by(func.count(AnalyticsEvent.id).desc())
        )).all()
        source_rows = (await db.execute(
            select(UserAcquisition.source, func.count(UserAcquisition.id))
            .group_by(UserAcquisition.source)
            .order_by(func.count(UserAcquisition.id).desc())
        )).all()

    conversion = round(first_analyses / registrations * 100, 1) if registrations else 0.0
    pay_conversion = round(payment_success / payment_started * 100, 1) if payment_started else 0.0
    referral_conversion = round(referral_activated / referral_invited * 100, 1) if referral_invited else 0.0
    return {
        'users_total': users_total,
        'new_today': new_today,
        'new_7d': new_7d,
        'registrations': registrations,
        'first_analyses': first_analyses,
        'start_to_first_analysis': conversion,
        'mini_app_opens_7d': mini_app_opens,
        'analysis_success_7d': success_7d,
        'analysis_failed_7d': failed_7d,
        'avg_processing_ms_7d': avg_processing,
        'errors_7d': errors_7d,
        'payment_started_7d': payment_started,
        'payment_success_7d': payment_success,
        'payment_conversion_7d': pay_conversion,
        'stars_30d': stars_30d,
        'referral_invited': referral_invited,
        'referral_activated': referral_activated,
        'referral_conversion': referral_conversion,
        'material_types_7d': [{'type': key or 'other', 'count': int(count)} for key, count in type_rows],
        'sources': [{'source': source or 'direct', 'count': int(count)} for source, count in source_rows],
    }
