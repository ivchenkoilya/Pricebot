from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config.settings import Settings
from app.database.models import Notification, PriceHistory, Product, Watch
from app.utils.money import format_money


async def _already_sent(session: AsyncSession, watch_id: int, kind: str, price: Decimal | None, settings: Settings) -> bool:
    cutoff = datetime.utcnow() - timedelta(hours=settings.alert_cooldown_hours)
    stmt = select(Notification.id).where(Notification.watch_id == watch_id, Notification.type == kind, Notification.sent_at >= cutoff)
    if price is not None:
        stmt = stmt.where(Notification.price == price)
    return (await session.execute(stmt.limit(1))).scalar_one_or_none() is not None


async def evaluate_and_send(session: AsyncSession, bot: Bot, product: Product, previous_price: Decimal | None, previous_availability: str, settings: Settings) -> int:
    watches = (await session.execute(select(Watch).where(Watch.product_id == product.id, Watch.active.is_(True)).options(selectinload(Watch.user)))).scalars().all()
    if not watches:
        return 0
    previous_low = (await session.execute(select(func.min(PriceHistory.price)).where(PriceHistory.product_id == product.id, PriceHistory.is_test.is_(False), PriceHistory.price.is_not(None), PriceHistory.checked_at < (product.last_checked_at or datetime.utcnow())))).scalar_one_or_none()
    sent = 0
    for watch in watches:
        triggers: list[tuple[str, str]] = []
        cur = product.current_price
        if previous_price and cur and cur < previous_price:
            drop_pct = ((previous_price - cur) / previous_price * Decimal('100')).quantize(Decimal('0.1'))
            if watch.notify_any_drop and drop_pct >= Decimal(str(settings.min_drop_percent)):
                triggers.append(('price_drop', f'🔥 <b>ЦЕНА УПАЛА</b>\n\n{product.name}\n\nБыло: <s>{format_money(previous_price, product.currency)}</s>\nСейчас: <b>{format_money(cur, product.currency)}</b>\n\nЭкономия: {format_money(previous_price-cur, product.currency)}\n📉 −{drop_pct}%'))
        if watch.target_price and cur and cur <= watch.target_price:
            triggers.append(('target_price', f'🎯 <b>ЦЕЛЕВАЯ ЦЕНА ДОСТИГНУТА</b>\n\n{product.name}\n\nСейчас: <b>{format_money(cur, product.currency)}</b>\nТвоя цель: {format_money(watch.target_price, product.currency)}'))
        if watch.target_percent and watch.baseline_price and cur:
            threshold = watch.baseline_price * (Decimal('1') - watch.target_percent / Decimal('100'))
            if cur <= threshold:
                triggers.append(('target_percent', f'📉 {product.name}\nЦена упала минимум на {watch.target_percent}% от момента добавления.\nСейчас: <b>{format_money(cur, product.currency)}</b>'))
        if watch.notify_new_low and cur and previous_low and cur < previous_low:
            triggers.append(('new_low', f'🏆 <b>НОВЫЙ МИНИМУМ</b>\n\n{product.name}\n\nНовая минимальная цена: <b>{format_money(cur, product.currency)}</b>'))
        if watch.notify_in_stock and previous_availability != 'in_stock' and product.availability == 'in_stock':
            triggers.append(('in_stock', f'📦 <b>СНОВА В НАЛИЧИИ</b>\n\n{product.name}\nЦена: {format_money(cur, product.currency)}'))
        for kind, text in triggers:
            if await _already_sent(session, watch.id, kind, cur, settings):
                continue
            note = Notification(user_id=watch.user_id, watch_id=watch.id, type=kind, price=cur)
            session.add(note)
            await session.flush()
            try:
                kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🛒 Открыть товар', url=product.canonical_url)]])
                await bot.send_message(watch.user.telegram_id, text, reply_markup=kb)
                note.sent_at = datetime.utcnow()
                sent += 1
            except Exception:
                note.sent_at = None
            await session.commit()
    return sent
