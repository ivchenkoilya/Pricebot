from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.database.models import User
from app.database.razberi_models import AIUsage, ErrorLog, Material, Metric, RazberiPayment, Reminder
from app.services.copilot import build_inbox, query_terms, rank_materials
from app.services.core import clarify_plan, is_creator
from app.webapp.auth import TelegramWebAppUser, runtime_context, telegram_webapp_user


router = APIRouter(prefix='/api/copilot', tags=['clarify-copilot'])


class FeedbackBody(BaseModel):
    positive: bool
    feature: str = Field(default='answer', max_length=48)
    material_id: int | None = None


def _tg_namespace(tg: TelegramWebAppUser):
    return SimpleNamespace(id=tg.id, username=tg.username, first_name=tg.first_name or 'User')


async def _user(ctx, tg: TelegramWebAppUser):
    return await ctx.users.upsert(_tg_namespace(tg))


def _card(item, *, score: float | None = None, snippet: str = '') -> dict:
    result = {
        'id': item.id,
        'type': item.type,
        'title': item.title,
        'summary': item.summary,
        'created_at': item.created_at.isoformat() + 'Z' if item.created_at else None,
    }
    if score is not None:
        result['score'] = round(score, 2)
    if snippet:
        result['snippet'] = snippet
    return result


@router.get('/inbox')
async def copilot_inbox(request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    materials = await ctx.materials.latest(user.id, 24)
    async with ctx.db.sessions() as db:
        reminders = list((await db.execute(
            select(Reminder)
            .where(Reminder.user_id == user.id, Reminder.status == 'active')
            .order_by(Reminder.remind_at.asc())
            .limit(12)
        )).scalars())
    payload = build_inbox(materials, reminders, limit=7)
    payload['materials_scanned'] = len(materials)
    return payload


@router.get('/search')
async def copilot_search(
    request: Request,
    q: str = Query(min_length=2, max_length=240),
    limit: int = Query(8, ge=1, le=12),
    tg: TelegramWebAppUser = Depends(telegram_webapp_user),
):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    materials = await ctx.materials.latest(user.id, 80)
    hits = rank_materials(materials, q, limit=limit)
    return {'query': q, 'items': [_card(hit.item, score=hit.score, snippet=hit.snippet) for hit in hits]}


@router.get('/materials/{material_id}/related')
async def related_materials(
    material_id: int,
    request: Request,
    tg: TelegramWebAppUser = Depends(telegram_webapp_user),
):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    current = await ctx.materials.get(user.id, material_id)
    if not current:
        raise HTTPException(404, 'Материал не найден')
    pool = [item for item in await ctx.materials.latest(user.id, 70) if item.id != material_id]
    query = f'{current.title} {current.summary}'
    hits = rank_materials(pool, query, limit=4)
    # Avoid showing weak recency-only matches as "related".
    hits = [hit for hit in hits if hit.score >= 4.0]
    return {'items': [_card(hit.item, score=hit.score, snippet=hit.snippet) for hit in hits]}


@router.post('/materials/{material_id}/full')
async def full_analysis(
    material_id: int,
    request: Request,
    tg: TelegramWebAppUser = Depends(telegram_webapp_user),
):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    plan = clarify_plan(user, ctx.settings)
    if plan == 'FREE':
        raise HTTPException(403, '⚡ Полный разбор доступен в PRO и PRO MAX. Он собирает главное, действия, сроки, деньги и риски одним запросом.')
    item = await ctx.materials.get(user.id, material_id)
    if not item:
        raise HTTPException(404, 'Материал не найден')
    if not await ctx.usage.allowed(user):
        raise HTTPException(429, 'Лимит AI закончился. Открой «Тарифы» или докупи запросы.')

    context = await ctx.materials.context(
        user.id,
        material_id,
        'главное задачи действия сроки даты деньги суммы оплата риски штрафы обязательства',
        limit=7,
    )
    prompt = (
        'Сделай полный практический разбор материала за один проход. Не используй Markdown-символы вроде ** или ##. '
        'Формат строго такой, пропускай раздел только если в материале совсем нет данных:\n'
        'Кратко: 1–3 предложения.\n\n'
        'Главное:\n• ключевые факты\n\n'
        'Что делать:\n• конкретные следующие действия\n\n'
        'Сроки:\n• дата или срок — к чему относится\n\n'
        'Деньги:\n• сумма или условие оплаты — контекст\n\n'
        'Риски:\n• риск — почему это важно\n\n'
        'Не выдумывай факты и явно скажи, если важной информации нет.'
    )
    try:
        answer, usage = await ctx.ai.ask(prompt, context, model=ctx.settings.smart)
    except Exception as exc:
        await ctx.errors.record('copilot-full', tg.id, 'copilot_full', exc)
        raise HTTPException(502, 'Clarify временно не смог сделать полный разбор') from exc
    await ctx.usage.record(user.id, ctx.settings.smart, 'copilot_full', usage)
    await ctx.metrics.inc('copilot_full', user.id)
    return {'answer': answer, 'material_id': material_id, 'plan': plan}


@router.post('/feedback')
async def copilot_feedback(
    body: FeedbackBody,
    request: Request,
    tg: TelegramWebAppUser = Depends(telegram_webapp_user),
):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    name = 'answer_helpful' if body.positive else 'answer_unhelpful'
    await ctx.metrics.inc(name, user.id)
    # Feature/material id are intentionally encoded only as coarse metric names;
    # feedback must not copy the user's answer text into analytics.
    feature = ''.join(ch for ch in body.feature.lower() if ch.isalnum() or ch in '_-')[:28]
    if feature:
        await ctx.metrics.inc(f'{name}_{feature}'[:64], user.id)
    return {'ok': True}


@router.get('/admin/overview')
async def admin_overview(request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    if not is_creator(user, ctx.settings):
        raise HTTPException(403, 'Только для OWNER')

    now = datetime.utcnow()
    day = now - timedelta(hours=24)
    month = now - timedelta(days=30)
    async with ctx.db.sessions() as db:
        users_total = int((await db.execute(select(func.count(User.id)))).scalar_one())
        active_24h = int((await db.execute(select(func.count(User.id)).where(User.last_active_at >= day))).scalar_one())
        materials_total = int((await db.execute(select(func.count(Material.id)))).scalar_one())
        ai_24h = int((await db.execute(select(func.count(AIUsage.id)).where(AIUsage.created_at >= day))).scalar_one())
        errors_24h = int((await db.execute(select(func.count(ErrorLog.id)).where(ErrorLog.created_at >= day))).scalar_one())
        stars_30d = int((await db.execute(
            select(func.coalesce(func.sum(RazberiPayment.amount), 0)).where(
                RazberiPayment.created_at >= month,
                RazberiPayment.status == 'paid',
                RazberiPayment.currency == 'XTR',
            )
        )).scalar_one())
        helpful = int((await db.execute(select(func.coalesce(func.sum(Metric.value), 0)).where(Metric.name == 'answer_helpful', Metric.created_at >= month))).scalar_one())
        unhelpful = int((await db.execute(select(func.coalesce(func.sum(Metric.value), 0)).where(Metric.name == 'answer_unhelpful', Metric.created_at >= month))).scalar_one())
    return {
        'users_total': users_total,
        'active_24h': active_24h,
        'materials_total': materials_total,
        'ai_24h': ai_24h,
        'errors_24h': errors_24h,
        'stars_30d': stars_30d,
        'feedback': {'helpful': helpful, 'unhelpful': unhelpful},
    }
