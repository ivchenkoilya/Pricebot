from __future__ import annotations

from types import SimpleNamespace

from aiogram.types import LabeledPrice
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.core import bonus_requests, clarify_plan
from app.webapp.auth import TelegramWebAppUser, runtime_context, telegram_webapp_user

router = APIRouter(prefix='/api', tags=['clarify-plans-v2'])
SUBSCRIPTION_PERIOD_SECONDS = 2_592_000


class PlanInvoiceBody(BaseModel):
    product: str = Field(min_length=2, max_length=32)


def _tg_namespace(tg: TelegramWebAppUser):
    return SimpleNamespace(id=tg.id, username=tg.username, first_name=tg.first_name or 'User')


async def _user(ctx, tg: TelegramWebAppUser):
    return await ctx.users.upsert(_tg_namespace(tg))


def _catalog(settings) -> list[dict]:
    return [
        {
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
        {
            'code': 'PRO', 'title': 'PRO', 'price': settings.pro_stars_price, 'period': '30 дней',
            'daily_requests': settings.pro_daily_ai_limit,
            'voice_minutes': settings.pro_voice_max_seconds // 60,
            'document_pages': settings.pro_document_max_pages,
            'tagline': 'Для ежедневной работы',
            'features': [
                f'До {settings.pro_daily_ai_limit} AI-запросов в день',
                f'Голосовые до {settings.pro_voice_max_seconds // 60} минут',
                f'Документы до {settings.pro_document_max_pages} страниц',
                'Smart AI режим',
                'Длинные материалы, Memory, проекты и сравнения',
            ],
        },
        {
            'code': 'MAX', 'title': 'PRO MAX', 'price': settings.max_stars_price, 'period': '30 дней',
            'daily_requests': settings.max_daily_ai_limit,
            'voice_minutes': settings.max_voice_max_seconds // 60,
            'document_pages': settings.max_document_max_pages,
            'tagline': 'Максимум для активной работы',
            'features': [
                f'До {settings.max_daily_ai_limit} AI-запросов в день',
                f'Голосовые до {settings.max_voice_max_seconds // 60} минут',
                f'Документы до {settings.max_document_max_pages} страниц',
                'Smart AI режим',
                'Максимальные лимиты Clarify и приоритетная работа',
            ],
        },
    ]


def _packs(settings) -> list[dict]:
    return [
        {'product': 'pack50', 'requests': 50, 'price': settings.request_pack_50_stars, 'title': '+50 запросов'},
        {'product': 'pack150', 'requests': 150, 'price': settings.request_pack_150_stars, 'title': '+150 запросов'},
        {'product': 'pack500', 'requests': 500, 'price': settings.request_pack_500_stars, 'title': '+500 запросов'},
    ]


def _product(settings, product: str) -> dict | None:
    product = (product or '').lower().strip()
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
        raise HTTPException(400, 'Этот пакет обновлён. Обнови вкладку «Тарифы».')

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
            'description': f'{credits} дополнительных AI-запросов. Не сгорают и расходуются после лимита тарифа.',
            'payload': f'clarify_pack:{credits}:{user.id}',
            'prices': [LabeledPrice(label=f'+{credits} запросов', amount=item['price'])],
        })
    return await ctx.bot.create_invoice_link(**kwargs)


@router.get('/plans')
async def plans(request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    await ctx.metrics.inc('plans_open', user.id)
    return {
        'current': clarify_plan(user, ctx.settings),
        'pro_until': user.pro_until.isoformat() + 'Z' if user.pro_until else None,
        'bonus_requests': bonus_requests(user),
        'plans': _catalog(ctx.settings),
        'packs': _packs(ctx.settings),
        'note': 'Дополнительные запросы не сгорают и начинают расходоваться только после обычного лимита тарифа.',
    }


@router.post('/plans/invoice')
async def plans_invoice(body: PlanInvoiceBody, request: Request, tg: TelegramWebAppUser = Depends(telegram_webapp_user)):
    ctx = runtime_context(request)
    user = await _user(ctx, tg)
    link = await _invoice_link(ctx, user, body.product)
    await ctx.metrics.inc('plans_purchase_click', user.id)
    return {'invoice_url': link}
