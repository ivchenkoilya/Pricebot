from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from aiogram.types import LabeledPrice
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select

from app.database.models import User
from app.database.razberi_models import Material, Project, ProjectMaterial, Reminder
from app.services.core import (
    bonus_requests,
    clarify_plan,
    is_active_pro,
    is_creator,
    plan_daily_ai_limit,
)
from app.services.reminders import parse_reminder
from app.webapp.auth import TelegramWebAppUser, runtime_context, telegram_webapp_user

router = APIRouter(prefix='/api', tags=['clarify-webapp'])
SUBSCRIPTION_PERIOD_SECONDS = 2_592_000
PAGE_RE = re.compile(r'\[Страница\s+(\d+)\]', re.I)
METRICS = {
    'webapp_open', 'material_open', 'material_question', 'material_action', 'project_open',
    'compare_run', 'pro_page_open', 'pro_purchase_click', 'plans_open', 'plans_purchase_click',
    'reminder_created', 'compose_run', 'materials_cleared',
}


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=3000)


class ActionBody(BaseModel):
    action: str = Field(min_length=1, max_length=32)


class ProjectBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class CompareBody(BaseModel):
    first_id: int
    second_id: int


class ReminderBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    remind_at: str | None = None


class ReminderPatch(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=2000)
    remind_at: str | None = None
    status: str | None = None


class ComposeBody(BaseModel):
    brief: str = Field(min_length=1, max_length=6000)


class RewriteBody(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    mode: str = Field(min_length=1, max_length=80)


class SettingsBody(BaseModel):
    timezone: str | None = Field(default=None, max_length=64)
    style: str | None = Field(default=None, max_length=1000)
    ai_mode: str | None = None


class MetricBody(BaseModel):
    name: str


class PlanInvoiceBody(BaseModel):
    product: str = Field(min_length=2, max_length=32)


def _tg_namespace(tg: TelegramWebAppUser):
    return SimpleNamespace(id=tg.id, username=tg.username, first_name=tg.first_name or 'User')


async def _user(ctx, tg: TelegramWebAppUser):
    return await ctx.users.upsert(_tg_namespace(tg))


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() + 'Z' if value else None


def _material_card(item: Material) -> dict:
    return {
        'id': item.id,
        'type': item.type,
        'title': item.title,
        'summary': item.summary,
        'status': item.status,
        'created_at': _dt(item.created_at),
    }


def _sources(context: str, title: str) -> list[dict]:
    pages: list[int] = []
    for raw in PAGE_RE.findall(context or ''):
        page = int(raw)
        if page not in pages:
            pages.append(page)
    return [{'title': title, 'page': page} for page in pages[:8]]


def _settings_json(user: User) -> dict:
    try:
        value = json.loads(user.notification_settings or '{}')
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _parse_remind_at(value: str, timezone_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise HTTPException(400, 'Неверная дата напоминания') from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _catalog(settings) -> dict[str, dict]:
    return {
        'free': {
            'code': 'FREE', 'title': 'FREE', 'price': 0, 'period': 'навсегда',
            'daily_requests': settings.free_daily_ai_limit,
            'voice_minutes': settings.free_voice_max_seconds // 60,
            'document_pages': settings.free_document_max_pages,
            'tagline': 'Для знакомства с Clarify',
            'features': [
                f'{settings.free_daily_ai_limit} AI-запросов в день',
                f'Голосовые до {settings.free_voice_max_seconds // 60} минут',
                f'Документы до {settings.free_document_max_pages} страниц',
                'Memory и базовые быстрые действия',
                'Fast AI режим',
            ],
        },
        'pro': {
            'code': 'PRO', 'title': 'PRO', 'price': settings.pro_stars_price, 'period': '30 дней',
            'daily_requests': settings.pro_daily_ai_limit,
            'voice_minutes': settings.pro_voice_max_seconds // 60,
            'document_pages': settings.pro_document_max_pages,
            'tagline': 'Для ежедневной работы',
            'features': [
                f'{settings.pro_daily_ai_limit} AI-запросов в день',
                f'Голосовые до {settings.pro_voice_max_seconds // 60} минут',
                f'Документы до {settings.pro_document_max_pages} страниц',
                'Smart AI режим',
                'Длинные материалы, Memory, проекты и сравнения',
            ],
        },
        'max': {
            'code': 'MAX', 'title': 'PRO MAX', 'price': settings.max_stars_price, 'period': '30 дней',
            'daily_requests': settings.max_daily_ai_limit,
            'voice_minutes': settings.max_voice_max_seconds // 60,
            'document_pages': settings.max_document_max_pages,
            'tagline': 'Максимум для активной работы',
            'features': [
                f'{settings.max_daily_ai_limit} AI-запросов в день',
                f'Голосовые до {settings.max_voice_max_seconds // 60} минут',
                f'Документы до {settings.max_document_max_pages} страниц',
                'Smart AI режим',
                'Максимальные лимиты Clarify без постоянных стопов',
            ],
        },
    }


def _packs(settings) -> list[dict]:
    return [
        {'product': 'pack100', 'requests': 100, 'price': settings.request_pack_100_stars, 'title': '+100 запросов'},
        {'product': 'pack500', 'requests': 500, 'price': settings.request_pack_500_stars, 'title': '+500 запросов'},
        {'product': 'pack2000', 'requests': 2000, 'price': settings.request_pack_2000_stars, 'title': '+2000 запросов'},
    ]


def _product(settings, product: str) -> dict | None:
    product = product.lower().strip()
    if product == 'pro':
        return {'kind': 'plan', 'plan': 'PRO', 'price': settings.pro_stars_price, 'title': 'Clarify PRO', 'label': 'PRO · 30 дней'}
    if product == 'max':
        return {'kind': 'plan', 'plan': 'MAX', 'price': settings.max_stars_price, 'title': 'Clarify PRO MAX', 'label': 'PRO MAX · 30 дней'}
    for item in _packs(settings):
        if item['product'] == product:
            return {'kind': 'pack', **item}
    return None


async def _invoice_link(ctx, user, product: str) -> str:
    item = _product(ctx.settings, product)
    if not item:
        raise HTTPException(400, 'Неизвестный тариф или пакет')
    if is_creator(user, ctx.settings) and item['kind'] == 'plan':
        raise HTTPException(400, 'OWNER уже имеет Unlimited-доступ')

    kwargs = {
        'title': item['title'],
        'provider_token': '',
        'currency': 'XTR',
    }
    if item['kind'] == 'plan':
        code = item['plan'].lower()
        kwargs.update({
            'description': f'{item["title"]} на 30 дней с автоматическим продлением',
            'payload': f'clarify_plan:{code}:{user.id}',
            'prices': [LabeledPrice(label=item['label'], amount=item['price'])],
            'subscription_period': SUBSCRIPTION_PERIOD_SECONDS,
        })
    else:
        credits = int(item['requests'])
        kwargs.update({
            'description': f'{credits} дополнительных AI-запросов. Не сгорают в конце дня.',
            'payload': f'clarify_pack:{credits}:{user.id}',
            'prices': [LabeledPrice(label=f'+{credits} запросов', amount=item['price'])],
        })
    return await ctx.bot.create_invoice_link(**kwargs)


@router.get('/me')
async def me(request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    owner = is_creator(user, ctx.settings)
    used = await ctx.usage.ai_count_today(user.id)
    plan = clarify_plan(user, ctx.settings)
    limit = plan_daily_ai_limit(user, ctx.settings)
    style = await ctx.styles.get(user.id)
    await ctx.metrics.inc('webapp_open', user.id)
    return {
        'telegram_id': user.telegram_id,
        'first_name': user.first_name or tg.first_name,
        'username': user.username,
        'owner': owner,
        'plan': plan,
        'pro_until': _dt(user.pro_until),
        'usage': {'used': used, 'limit': limit, 'bonus': bonus_requests(user)},
        'timezone': user.timezone or ctx.settings.default_timezone,
        'style': style,
        'ai_mode': _settings_json(user).get('clarify_ai_mode', 'fast'),
        'version': ctx.settings.version,
        'pro_price': ctx.settings.pro_stars_price,
        'max_price': ctx.settings.max_stars_price,
    }


@router.get('/materials')
async def materials(
    request: Request,
    tg: TelegramWebAppUser = Depends(telegram_webapp_user),
    cursor: int | None = None,
    limit: int = Query(20, ge=1, le=50),
    type: str | None = Query(None, max_length=32),
    q: str | None = Query(None, max_length=200),
    period: str = Query('all', pattern='^(today|week|all)$'),
):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    conditions = [Material.user_id == user.id]
    if cursor:
        conditions.append(Material.id < cursor)
    if type and type != 'all':
        groups = {
            'documents': ['pdf', 'docx', 'txt', 'md', 'xlsx', 'csv', 'document', 'spreadsheet'],
            'voice': ['voice', 'audio'],
            'images': ['image', 'screenshot'],
            'links': ['link'],
            'text': ['text', 'forwarded', 'draft'],
        }
        conditions.append(Material.type.in_(groups.get(type, [type])))
    if period == 'today':
        conditions.append(Material.created_at >= datetime.utcnow() - timedelta(days=1))
    elif period == 'week':
        conditions.append(Material.created_at >= datetime.utcnow() - timedelta(days=7))
    if q:
        needle = f'%{q.strip()}%'
        conditions.append(or_(Material.title.ilike(needle), Material.summary.ilike(needle), Material.extracted_text.ilike(needle)))
    async with ctx.db.sessions() as db:
        rows = list((await db.execute(select(Material).where(*conditions).order_by(Material.id.desc()).limit(limit + 1))).scalars())
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {'items': [_material_card(item) for item in rows], 'next_cursor': rows[-1].id if has_more and rows else None}


@router.delete('/materials')
async def delete_all_materials(request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    count = await ctx.materials.delete_user_materials(user.id)
    await ctx.conversations.clear(user.id)
    await ctx.metrics.inc('materials_cleared', user.id, max(1, count))
    return {'ok': True, 'deleted': count}


@router.get('/materials/{material_id}')
async def material_detail(material_id: int, request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    item = await ctx.materials.get(user.id, material_id)
    if not item:
        raise HTTPException(404, 'Материал не найден')
    await ctx.metrics.inc('material_open', user.id)
    return {
        **_material_card(item),
        'text': item.extracted_text[:80_000],
        'available_actions': ['summary', 'main', 'tasks', 'risks', 'money', 'dates', 'plain', 'wants', 'reply'],
    }


@router.post('/materials/{material_id}/ask')
async def ask_material(material_id: int, body: AskBody, request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    item = await ctx.materials.get(user.id, material_id)
    if not item:
        raise HTTPException(404, 'Материал не найден')
    if not await ctx.usage.allowed(user):
        raise HTTPException(429, 'Лимит AI закончился. Открой «Тарифы» или докупи пакет запросов.')
    context = await ctx.materials.context(user.id, material_id, body.question)
    try:
        answer, usage = await ctx.ai.ask(body.question, context, model=ctx.settings.smart)
    except Exception as exc:
        await ctx.errors.record(uuid.uuid4().hex, tg.id, 'webapp_material_ask', exc)
        raise HTTPException(502, 'Clarify временно не смог сформировать ответ') from exc
    await ctx.usage.record(user.id, ctx.settings.smart, 'webapp_material_qa', usage)
    await ctx.metrics.inc('material_question', user.id)
    return {'answer': answer, 'sources': _sources(context, item.title)}


@router.post('/materials/{material_id}/action')
async def material_action(material_id: int, body: ActionBody, request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    item = await ctx.materials.get(user.id, material_id)
    if not item:
        raise HTTPException(404, 'Материал не найден')
    if body.action == 'summary':
        return {'answer': item.summary or 'Краткое содержание пока не сохранено.', 'sources': []}
    if not await ctx.usage.allowed(user):
        raise HTTPException(429, 'Лимит AI закончился. Открой «Тарифы» или докупи пакет запросов.')
    actions = {
        'main': ('Перечисли самое важное краткими пунктами.', 'главное ключевые факты', False),
        'tasks': ('Перечисли конкретные задачи и следующие действия. Если их нет — скажи это.', 'задача действие обязанность', False),
        'risks': ('Найди риски, штрафы, ограничения и потенциально невыгодные условия. Только факты из материала.', 'риск штраф пеня ответственность', True),
        'money': ('Собери денежные условия: цены, суммы, оплату, комиссии и штрафы с контекстом.', 'цена сумма оплата штраф', False),
        'dates': ('Собери сроки и даты и поясни, к чему относится каждый срок.', 'срок дата дедлайн', False),
        'plain': ('Объясни материал простыми словами без канцелярита, сохрани факты и ограничения.', 'главное условия обязанности', False),
        'wants': ('Скажи конкретно, что от пользователя хотят и что ему нужно сделать.', 'требуется сделать ответ подтвердить', False),
        'reply': ('Подготовь короткий естественный ответ отправителю. Верни только готовый ответ.', 'сообщение вопрос отправитель', False),
    }
    selected = actions.get(body.action)
    if not selected:
        raise HTTPException(400, 'Неизвестное действие')
    prompt, query, deep = selected
    context = await ctx.materials.context(user.id, material_id, query)
    model = ctx.settings.smart if deep else ctx.settings.fast
    try:
        answer, usage = await ctx.ai.ask(prompt, context, model=model)
    except Exception as exc:
        await ctx.errors.record(uuid.uuid4().hex, tg.id, 'webapp_material_action', exc)
        raise HTTPException(502, 'Clarify временно не смог выполнить действие') from exc
    await ctx.usage.record(user.id, model, f'webapp_{body.action}', usage)
    await ctx.metrics.inc('material_action', user.id)
    return {'answer': answer, 'sources': _sources(context, item.title)}


@router.delete('/materials/{material_id}')
async def delete_material(material_id: int, request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    if not await ctx.materials.delete(user.id, material_id):
        raise HTTPException(404, 'Материал не найден')
    return {'ok': True}


@router.get('/projects')
async def projects(request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    async with ctx.db.sessions() as db:
        rows = (await db.execute(
            select(Project, func.count(ProjectMaterial.id))
            .outerjoin(ProjectMaterial, ProjectMaterial.project_id == Project.id)
            .where(Project.user_id == user.id)
            .group_by(Project.id)
            .order_by(Project.created_at.desc())
        )).all()
    return {'items': [{'id': p.id, 'name': p.name, 'count': int(count), 'created_at': _dt(p.created_at)} for p, count in rows]}


@router.post('/projects')
async def create_project(body: ProjectBody, request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    project = await ctx.projects.create(user.id, body.name)
    return {'id': project.id, 'name': project.name}


@router.get('/projects/{project_id}')
async def project_detail(project_id: int, request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    project, items = await ctx.projects.materials(user.id, project_id)
    if not project:
        raise HTTPException(404, 'Проект не найден')
    await ctx.metrics.inc('project_open', user.id)
    return {'id': project.id, 'name': project.name, 'materials': [_material_card(item) for item in items]}


@router.post('/projects/{project_id}/materials/{material_id}')
async def add_project_material(project_id: int, material_id: int, request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    if not await ctx.projects.add_material(user.id, project_id, material_id):
        raise HTTPException(404, 'Проект или материал не найден')
    return {'ok': True}


@router.post('/projects/{project_id}/ask')
async def ask_project(project_id: int, body: AskBody, request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    project, items = await ctx.projects.materials(user.id, project_id)
    if not project:
        raise HTTPException(404, 'Проект не найден')
    if not await ctx.usage.allowed(user):
        raise HTTPException(429, 'Лимит AI закончился. Открой «Тарифы» или докупи пакет запросов.')
    parts = []
    sources = []
    for item in items[:12]:
        context = await ctx.materials.context(user.id, item.id, body.question, limit=3)
        if context:
            parts.append(f'### {item.title}\n{context}')
            sources.extend(_sources(context, item.title))
    if not parts:
        raise HTTPException(400, 'В проекте пока нет материалов')
    answer, usage = await ctx.ai.ask(body.question, '\n\n'.join(parts)[:48_000], model=ctx.settings.smart)
    await ctx.usage.record(user.id, ctx.settings.smart, 'webapp_project_qa', usage)
    return {'answer': answer, 'sources': sources[:12]}


@router.post('/compare')
async def compare(body: CompareBody, request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    if body.first_id == body.second_id:
        raise HTTPException(400, 'Выбери два разных материала')
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    first = await ctx.materials.get(user.id, body.first_id)
    second = await ctx.materials.get(user.id, body.second_id)
    if not first or not second:
        raise HTTPException(404, 'Материал не найден')
    if not await ctx.usage.allowed(user):
        raise HTTPException(429, 'Лимит AI закончился. Открой «Тарифы» или докупи пакет запросов.')
    a = await ctx.materials.context(user.id, first.id, 'цена срок обязательства риск отличие', limit=5)
    b = await ctx.materials.context(user.id, second.id, 'цена срок обязательства риск отличие', limit=5)
    answer, usage = await ctx.ai.compare(first.title, a, second.title, b)
    await ctx.usage.record(user.id, ctx.settings.smart, 'webapp_compare', usage)
    await ctx.metrics.inc('compare_run', user.id)
    return {'answer': answer, 'first': _material_card(first), 'second': _material_card(second)}


@router.get('/reminders')
async def reminders(request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    async with ctx.db.sessions() as db:
        rows = list((await db.execute(select(Reminder).where(Reminder.user_id == user.id).order_by(Reminder.remind_at.asc()))).scalars())
    return {'items': [{'id': r.id, 'text': r.text, 'remind_at': _dt(r.remind_at), 'status': r.status} for r in rows]}


@router.post('/reminders')
async def create_reminder(body: ReminderBody, request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    if body.remind_at:
        task, when = body.text.strip(), _parse_remind_at(body.remind_at, user.timezone or ctx.settings.default_timezone)
    else:
        parsed = parse_reminder(body.text, user.timezone or ctx.settings.default_timezone)
        if not parsed:
            raise HTTPException(400, 'Не понял дату напоминания')
        task, when = parsed
    item = await ctx.reminders.create_pending(user.id, task, when)
    await ctx.reminders.activate(user.id, item.id)
    await ctx.metrics.inc('reminder_created', user.id)
    return {'id': item.id, 'text': task, 'remind_at': _dt(when), 'status': 'active'}


@router.patch('/reminders/{reminder_id}')
async def patch_reminder(reminder_id: int, body: ReminderPatch, request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    async with ctx.db.sessions() as db:
        item = (await db.execute(select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == user.id))).scalar_one_or_none()
        if not item:
            raise HTTPException(404, 'Напоминание не найдено')
        if body.text is not None:
            item.text = body.text.strip()
        if body.remind_at is not None:
            item.remind_at = _parse_remind_at(body.remind_at, user.timezone or ctx.settings.default_timezone)
        if body.status in {'active', 'cancelled'}:
            item.status = body.status
        await db.commit()
    return {'ok': True}


@router.delete('/reminders/{reminder_id}')
async def delete_reminder(reminder_id: int, request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    async with ctx.db.sessions() as db:
        result = await db.execute(delete(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == user.id))
        await db.commit()
    if not result.rowcount:
        raise HTTPException(404, 'Напоминание не найдено')
    return {'ok': True}


@router.post('/compose')
async def compose(body: ComposeBody, request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    if not await ctx.usage.allowed(user):
        raise HTTPException(429, 'Лимит AI закончился. Открой «Тарифы» или докупи пакет запросов.')
    style = await ctx.styles.get(user.id)
    answer, usage = await ctx.ai.compose(body.brief, style)
    await ctx.usage.record(user.id, ctx.settings.fast, 'webapp_compose', usage)
    await ctx.metrics.inc('compose_run', user.id)
    return {'answer': answer}


@router.post('/rewrite')
async def rewrite(body: RewriteBody, request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    if not await ctx.usage.allowed(user):
        raise HTTPException(429, 'Лимит AI закончился. Открой «Тарифы» или докупи пакет запросов.')
    answer, usage = await ctx.ai.rewrite(body.text, body.mode)
    await ctx.usage.record(user.id, ctx.settings.fast, 'webapp_rewrite', usage)
    return {'answer': answer}


@router.get('/settings')
async def settings_get(request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    return await me(request, tg)


@router.patch('/settings')
async def settings_patch(body: SettingsBody, request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    if body.timezone:
        try:
            ZoneInfo(body.timezone)
        except Exception as exc:
            raise HTTPException(400, 'Неизвестный часовой пояс') from exc
        async with ctx.db.sessions() as db:
            row = (await db.execute(select(User).where(User.id == user.id))).scalar_one()
            row.timezone = body.timezone
            await db.commit()
    if body.style is not None:
        await ctx.styles.set(user.id, body.style)
    if body.ai_mode in {'fast', 'smart'}:
        if body.ai_mode == 'smart' and clarify_plan(user, ctx.settings) == 'FREE':
            raise HTTPException(403, 'Smart AI доступен в PRO и PRO MAX')
        async with ctx.db.sessions() as db:
            row = (await db.execute(select(User).where(User.id == user.id))).scalar_one()
            data = _settings_json(row)
            data['clarify_ai_mode'] = body.ai_mode
            row.notification_settings = json.dumps(data, ensure_ascii=False)
            await db.commit()
    return {'ok': True}


@router.get('/plans')
async def plans(request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    await ctx.metrics.inc('plans_open', user.id)
    return {
        'current': clarify_plan(user, ctx.settings),
        'pro_until': _dt(user.pro_until),
        'bonus_requests': bonus_requests(user),
        'plans': list(_catalog(ctx.settings).values()),
        'packs': _packs(ctx.settings),
        'note': 'Дополнительные запросы начинают расходоваться только после дневного лимита тарифа.',
    }


@router.post('/plans/invoice')
async def plans_invoice(body: PlanInvoiceBody, request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    link = await _invoice_link(ctx, user, body.product)
    await ctx.metrics.inc('plans_purchase_click', user.id)
    return {'invoice_url': link}


@router.get('/pro')
async def pro(request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    await ctx.metrics.inc('pro_page_open', user.id)
    return {
        'owner': is_creator(user, ctx.settings),
        'active': is_creator(user, ctx.settings) or is_active_pro(user),
        'plan': clarify_plan(user, ctx.settings),
        'price': ctx.settings.pro_stars_price,
        'pro_until': _dt(user.pro_until),
    }


@router.post('/pro/invoice')
async def pro_invoice(request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    link = await _invoice_link(ctx, user, 'pro')
    await ctx.metrics.inc('pro_purchase_click', user.id)
    return {'invoice_url': link}


@router.post('/metrics')
async def metric(body: MetricBody, request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    if body.name not in METRICS:
        raise HTTPException(400, 'Unknown metric')
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    await ctx.metrics.inc(body.name, user.id)
    return {'ok': True}


@router.delete('/me/data')
async def delete_my_data(request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    await ctx.privacy.delete_user_data(user.id)
    return {'ok': True}
