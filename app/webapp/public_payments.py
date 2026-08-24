from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.database.models import User
from app.payments.yookassa import YooKassaClient, YooKassaError
from app.webapp.auth import runtime_context


router = APIRouter(prefix='/public-api/payments', tags=['clarify-public-payments'])
_EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


class CheckoutBody(BaseModel):
    plan: str = Field(default='pro', min_length=3, max_length=8)
    telegram_id: int | None = None
    username: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=254)


def _price(plan: str) -> int:
    key = 'MAX_RUB_PRICE' if plan == 'max' else 'PRO_RUB_PRICE'
    default = 499 if plan == 'max' else 299
    try:
        return max(1, int((os.getenv(key) or str(default)).strip()))
    except ValueError:
        return default


def _public_base_url(request: Request) -> str:
    configured = (os.getenv('PUBLIC_SITE_URL') or '').strip().rstrip('/')
    if configured.startswith('https://'):
        return configured
    forwarded_proto = request.headers.get('x-forwarded-proto', '').split(',')[0].strip()
    forwarded_host = request.headers.get('x-forwarded-host', '').split(',')[0].strip()
    if forwarded_host:
        proto = forwarded_proto or 'https'
        return f'{proto}://{forwarded_host}'.rstrip('/')
    return str(request.base_url).rstrip('/')


async def _find_user(ctx, body: CheckoutBody) -> User:
    async with ctx.db.sessions() as db:
        if body.telegram_id and body.telegram_id > 0:
            user = (
                await db.execute(select(User).where(User.telegram_id == int(body.telegram_id)))
            ).scalar_one_or_none()
            if user is not None:
                return user

        username = (body.username or '').strip().lstrip('@').strip()
        if username:
            user = (
                await db.execute(
                    select(User)
                    .where(func.lower(User.username) == username.lower())
                    .order_by(User.last_active_at.desc())
                )
            ).scalars().first()
            if user is not None:
                return user

    raise HTTPException(
        404,
        'Не нашёл этот аккаунт Clarify. Сначала открой бота в Telegram хотя бы один раз, затем повтори оплату.',
    )


@router.get('/status')
async def payment_status(request: Request):
    client = YooKassaClient(request.app.state.settings)
    return {'enabled': client.configured}


@router.post('/create')
async def create_payment(body: CheckoutBody, request: Request):
    plan = (body.plan or 'pro').strip().lower()
    if plan not in {'pro', 'max'}:
        raise HTTPException(400, 'Неизвестный тариф.')

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

    price = _price(plan)
    label = 'Clarify PRO MAX' if plan == 'max' else 'Clarify PRO'
    base_url = _public_base_url(request)
    return_url = (os.getenv('YOOKASSA_RETURN_URL') or '').strip() or f'{base_url}/payment/success'

    try:
        checkout = await client.create_payment(
            amount_rub=price,
            description=f'{label} · 30 дней',
            return_url=return_url,
            metadata={
                'clarify_user_id': str(user.id),
                'telegram_id': str(user.telegram_id),
                'plan': plan,
                'source': 'clarify_public_site',
            },
            customer_email=email or None,
        )
    except YooKassaError as exc:
        await ctx.errors.record(uuid.uuid4().hex, user.telegram_id, 'yookassa_create', exc)
        raise HTTPException(502, str(exc)) from exc

    await ctx.metrics.inc('yookassa_checkout_created', user.id)
    return {
        'payment_id': checkout.payment_id,
        'status': checkout.status,
        'confirmation_url': checkout.confirmation_url,
    }


@router.post('/yookassa/webhook')
async def yookassa_webhook(request: Request):
    """Verify YooKassa webhook by fetching the payment from YooKassa itself."""
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

    obj = event.get('object') or {}
    payment_id = str(obj.get('id') or '').strip()
    event_name = str(event.get('event') or '')
    if not payment_id:
        raise HTTPException(400, 'Missing payment id')
    if event_name not in {'payment.succeeded', 'payment.canceled', 'payment.waiting_for_capture'}:
        return {'ok': True, 'ignored': event_name or 'unknown'}

    # Do not trust amount, user id or plan from the callback body. Pull the
    # canonical payment over authenticated YooKassa API first.
    try:
        payment = await client.get_payment(payment_id)
    except YooKassaError as exc:
        raise HTTPException(502, str(exc)) from exc

    status = str(payment.get('status') or '')
    if status != 'succeeded':
        return {'ok': True, 'status': status}

    metadata = payment.get('metadata') or {}
    if not isinstance(metadata, dict):
        raise HTTPException(400, 'Missing payment metadata')
    try:
        user_id = int(metadata.get('clarify_user_id') or 0)
    except (TypeError, ValueError):
        user_id = 0
    plan = 'MAX' if str(metadata.get('plan') or '').lower() == 'max' else 'PRO'
    if user_id <= 0:
        raise HTTPException(400, 'Missing Clarify user id')

    charge_id = f'yookassa:{payment_id}'
    if await ctx.subscriptions.payment_exists(charge_id):
        return {'ok': True, 'status': 'already_processed'}

    async with ctx.db.sessions() as db:
        user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(404, 'Clarify user not found')

    amount_obj = payment.get('amount') or {}
    try:
        amount_kopecks = int((Decimal(str(amount_obj.get('value') or '0')) * 100).quantize(Decimal('1')))
    except (InvalidOperation, ValueError):
        amount_kopecks = 0
    if str(amount_obj.get('currency') or '').upper() != 'RUB' or amount_kopecks <= 0:
        raise HTTPException(400, 'Unexpected payment amount')

    expected_kopecks = _price('max' if plan == 'MAX' else 'pro') * 100
    if amount_kopecks != expected_kopecks:
        raise HTTPException(400, 'Payment amount does not match the selected plan')

    now = datetime.utcnow()
    current_until = user.pro_until if user.pro_until and user.pro_until > now else now
    expires_at = current_until + timedelta(days=30)
    await ctx.subscriptions.activate(
        user.id,
        charge_id,
        amount_kopecks,
        expires_at,
        False,
        plan=plan,
        currency='RUB',
    )
    await ctx.metrics.inc('yookassa_purchased', user.id, max(1, amount_kopecks // 100))

    label = 'PRO MAX' if plan == 'MAX' else 'PRO'
    try:
        await ctx.bot.send_message(
            user.telegram_id,
            f'✅ <b>Clarify {label}</b> активирован на 30 дней. Оплата через ЮKassa подтверждена.',
        )
    except Exception as exc:
        await ctx.errors.record(uuid.uuid4().hex, user.telegram_id, 'yookassa_notify', exc)

    return {'ok': True, 'status': 'activated'}
