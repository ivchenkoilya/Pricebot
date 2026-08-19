from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings
from app.database.models import MetricEvent, Subscription, User

SUBSCRIPTION_PERIOD_SECONDS = 2_592_000


async def build_pro_payment_keyboard(bot: Bot, settings: Settings) -> InlineKeyboardMarkup:
    link = await bot.create_invoice_link(
        title='PRICE PRO',
        description='До 50 товаров, частые проверки и расширенные уведомления на 30 дней.',
        payload='price_pro_monthly_v1',
        currency='XTR',
        prices=[LabeledPrice(label='PRICE PRO', amount=settings.pro_stars_price)],
        provider_token='',
        subscription_period=SUBSCRIPTION_PERIOD_SECONDS,
    )
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f'⭐ Подключить за {settings.pro_stars_price} Stars', url=link)]])


async def activate_from_payment(session: AsyncSession, user: User, message: Message) -> Subscription:
    payment = message.successful_payment
    if payment is None:
        raise ValueError('successful_payment missing')
    existing = (await session.execute(select(Subscription).where(
        Subscription.telegram_payment_charge_id == payment.telegram_payment_charge_id
    ))).scalar_one_or_none()
    expiration_ts = getattr(payment, 'subscription_expiration_date', None)
    expires = datetime.utcfromtimestamp(expiration_ts) if expiration_ts else datetime.utcnow() + timedelta(days=30)
    if existing:
        existing.expires_at = max(existing.expires_at, expires)
        existing.status = 'active'
        existing.stars_amount = payment.total_amount
        user.is_pro = True
        user.pro_until = existing.expires_at
        session.add(MetricEvent(user_id=user.id, event='pro_renewed'))
        await session.commit()
        return existing
    sub = Subscription(
        user_id=user.id,
        telegram_payment_charge_id=payment.telegram_payment_charge_id,
        stars_amount=payment.total_amount,
        started_at=datetime.utcnow(),
        expires_at=expires,
        status='active',
    )
    session.add(sub)
    user.is_pro = True
    user.pro_until = expires
    session.add(MetricEvent(user_id=user.id, event='pro_purchased'))
    await session.commit()
    return sub
