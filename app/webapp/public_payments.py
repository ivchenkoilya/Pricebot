from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.database.models import User
from app.database.razberi_models import RazberiPayment
from app.payments.yookassa import YooKassaClient, YooKassaError
from app.webapp.auth import runtime_context

router = APIRouter(prefix='/public-api/payments', tags=['clarify-public-payments'])
_EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')

_PRODUCTS = {
    'pro': {'kind': 'plan', 'plan': 'PRO', 'description': 'Clarify PRO · 30 дней', 'env': 'PRO_RUB_PRICE', 'price': 299},
    'max': {'kind': 'plan', 'plan': 'MAX', 'description': 'Clarify PRO MAX · 30 дней', 'env': 'MAX_RUB_PRICE', 'price': 499},
    'pack50': {'kind': 'pack', 'credits': 50, 'description': '50 дополнительных AI-запросов Clarify', 'env': 'PACK_50_RUB_PRICE', 'price': 50},
    'pack150': {'kind': 'pack', 'credits': 150, 'description': '150 дополнительных AI-запросов Clarify', 'env': 'PACK_150_RUB_PRICE', 'price': 150},
    'pack500': {'kind': 'pack', 'credits': 500, 'description': '500 дополнительных AI-запросов Clarify', 'env': 'PACK_500_RUB_PRICE', 'price': 500},
}


class CheckoutBody(BaseModel):
    plan: str = Field(default='pro', min_length=3, max_length=8)
    telegram_id: int | None = None
    username: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=254)


def _product(code: str) -> dict | None:
    return _PRODUCTS.get((code or '').strip().lower())


def _price(code: str) -> int:
    item = _product(code)
    if not item:
        return 0
    try:
        return max(1, int((os.getenv(item['env']) or str(item['price'])).strip()))
    except ValueError:
        return int(item['price'])


def _public_base_url(request: Request) -> str:
    configured = (os.getenv('PUBLIC_SITE_URL') or '').strip().rstrip('/')
    if configured.startswith('https://'):
        return configured
    forwarded_proto = request.headers.get('x-forwarded-proto', '').split(',')[0].strip()
    forwarded_host = request.headers.get('x-forwarded-host', '').split(',')[0].strip()
    if forwarded_host:
        return f'{forwarded_proto or "https"}://{forwarded_host}'.rstrip('/')
    return str(request.base_url).rstrip('/')


async def _find_user(ctx, body: CheckoutBody) -> User:
    async with ctx.db.sessions() as db:
        if body.telegram_id and body.telegram_id > 0:
            user = (await db.execute(select(User).where(User.telegram_id == int(body.telegram_id)))).scalar_one_or_none()
            if user is not None:
                return user
        username = (body.username or '').strip().lstrip('@').strip()
        if username:
            user = (await db.execute(select(User).where(func.lower(User.username) == username.lower()).order_by(User.last_active_at.desc()))).scalars().first()
            if user is not None:
                return user
    raise HTTPException(404, 'Не нашёл этот аккаунт Clarify. Сначала открой бота в Telegram хотя бы один раз, затем повтори оплату.')


@router.get('/status')
async def payment_status(request: Request):
    return {'enabled': YooKassaClient(request.app.state.settings).configured}


@router.post('/create')
async def create_payment(body: CheckoutBody, request: Request):
    code = (body.plan or 'pro').strip().lower()
    item = _product(code)
    if item is None:
        raise HTTPException(400, 'Неизвестный тариф или пакет.')

    ctx = runtime_context(request)
    client = YooKassaClient(request.app.state.settings)
    if not client.configured:
        raise HTTPException(503, 'Оплата картой и СБП пока подключается.')

    user = await _find_user(ctx, body)
    email = (body.email or '').strip().lower()
    if email and not _EMAIL_RE.match(email):
        raise HTTPException(400, 'Проверь email для чека.')
    if client.vat_code > 0 and not email:
        raise HTTPException(400, 'Укажи email для электронного чека.')

    base_url = _public_base_url(request)
    return_url = (os.getenv('YOOKASSA_RETURN_URL') or '').strip() or f'{base_url}/payment/success'
    metadata = {
        'clarify_user_id': str(user.id),
        'telegram_id': str(user.telegram_id),
        'product': code,
        'kind': item['kind'],
        'source': 'clarify_public_site',
    }
    if item['kind'] == 'plan':
        metadata['plan'] = item['plan'].lower()
    else:
        metadata['credits'] = str(item['credits'])

    try:
        checkout = await client.create_payment(
            amount_rub=_price(code),
            description=item['description'],
            return_url=return_url,
            metadata=metadata,
            customer_email=email or None,
        )
    except YooKassaError as exc:
        await ctx.errors.record(uuid.uuid4().hex, user.telegram_id, 'yookassa_create', exc)
        raise HTTPException(502, str(exc)) from exc

    await ctx.metrics.inc('yookassa_checkout_created', user.id)
    return {'payment_id': checkout.payment_id, 'status': checkout.status, 'confirmation_url': checkout.confirmation_url}


@router.post('/yookassa/webhook')
async def yookassa_webhook(request: Request):
    ctx = runtime_context(request)
    client = YooKassaClient(request.app.state.settings)
    if not client.configured:
        raise HTTPException(503, 'YooKassa is not configured')

    try:
        event = await request.json()
    except Exception as exc:
        raise HTTPException(400, 'Invalid JSON') from exc
    if not isinstance(event, dict):
        raise HTTPException(400, 'Invalid event')

    payment_id = str((event.get('object') or {}).get('id') or '').strip()
    event_name = str(event.get('event') or '')
    if not payment_id:
        raise HTTPException(400, 'Missing payment id')
    if event_name not in {'payment.succeeded', 'payment.canceled', 'payment.waiting_for_capture'}:
        return {'ok': True, 'ignored': event_name or 'unknown'}

    try:
        payment = await client.get_payment(payment_id)
    except YooKassaError as exc:
        raise HTTPException(502, str(exc)) from exc
    if str(payment.get('status') or '') != 'succeeded':
        return {'ok': True, 'status': str(payment.get('status') or '')}

    metadata = payment.get('metadata') or {}
    try:
        user_id = int(metadata.get('clarify_user_id') or 0)
    except (TypeError, ValueError):
        user_id = 0
    if user_id <= 0:
        raise HTTPException(400, 'Missing Clarify user id')

    code = str(metadata.get('product') or metadata.get('plan') or '').strip().lower()
    item = _product(code)
    if item is None:
        raise HTTPException(400, 'Unknown Clarify product')

    charge_id = f'yookassa:{payment_id}'
    if await ctx.subscriptions.payment_exists(charge_id):
        return {'ok': True, 'status': 'already_processed'}

    amount_obj = payment.get('amount') or {}
    try:
        amount_kopecks = int((Decimal(str(amount_obj.get('value') or '0')) * 100).quantize(Decimal('1')))
    except (InvalidOperation, ValueError):
        amount_kopecks = 0
    if str(amount_obj.get('currency') or '').upper() != 'RUB' or amount_kopecks != _price(code) * 100:
        raise HTTPException(400, 'Payment amount does not match the selected product')

    async with ctx.db.sessions() as db:
        user = await db.get(User, user_id)
        if user is None:
            raise HTTPException(404, 'Clarify user not found')
        telegram_id = user.telegram_id
        current_pro_until = user.pro_until

    if item['kind'] == 'pack':
        credits = int(item['credits'])
        async with ctx.db.sessions() as db:
            user = await db.get(User, user_id)
            if user is None:
                raise HTTPException(404, 'Clarify user not found')
            data = {}
            try:
                parsed = json.loads(user.notification_settings or '{}')
                if isinstance(parsed, dict):
                    data = parsed
            except (TypeError, json.JSONDecodeError):
                pass
            balance = max(0, int(data.get('clarify_bonus_requests', 0) or 0)) + credits
            data['clarify_bonus_requests'] = balance
            user.notification_settings = json.dumps(data, ensure_ascii=False)
            db.add(RazberiPayment(
                user_id=user.id,
                telegram_charge_id=charge_id,
                currency='RUB',
                amount=amount_kopecks,
                status='paid',
                is_recurring=False,
            ))
            await db.commit()
        message = f'✅ <b>+{credits} запросов Clarify</b> начислено. Дополнительный баланс: <b>{balance}</b>.'
        result_status = 'credits_added'
    else:
        plan = item['plan']
        now = datetime.utcnow()
        current_until = current_pro_until if current_pro_until and current_pro_until > now else now
        expires_at = current_until + timedelta(days=30)
        await ctx.subscriptions.activate(user_id, charge_id, amount_kopecks, expires_at, False, plan=plan, currency='RUB')
        label = 'PRO MAX' if plan == 'MAX' else 'PRO'
        message = f'✅ <b>Clarify {label}</b> активирован на 30 дней. Оплата через ЮKassa подтверждена.'
        result_status = 'activated'

    await ctx.metrics.inc('yookassa_pack_purchased' if item['kind'] == 'pack' else 'yookassa_purchased', user_id)
    try:
        await ctx.bot.send_message(telegram_id, message)
    except Exception as exc:
        await ctx.errors.record(uuid.uuid4().hex, user_id, 'yookassa_notify', exc)

    return {'ok': True, 'status': result_status}
