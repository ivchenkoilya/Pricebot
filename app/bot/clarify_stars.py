from __future__ import annotations

import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message


def _star_value(value) -> float:
    """Convert Telegram StarAmount to a displayable number without assuming a minor aiogram version."""
    amount = int(getattr(value, 'amount', 0) or 0)
    nano = int(getattr(value, 'nanostar_amount', 0) or 0)
    return amount + nano / 1_000_000_000


def _format_stars(value) -> str:
    stars = _star_value(value)
    if stars == int(stars):
        return f'{int(stars):,}'.replace(',', ' ')
    return f'{stars:,.3f}'.replace(',', ' ').rstrip('0').rstrip('.')


def _partner_label(partner) -> str:
    if partner is None:
        return 'Telegram'

    user = getattr(partner, 'user', None)
    if user is not None:
        username = getattr(user, 'username', None)
        if username:
            return f'@{username}'
        name = getattr(user, 'full_name', None) or getattr(user, 'first_name', None)
        if name:
            return str(name)

    cls = partner.__class__.__name__
    labels = {
        'TransactionPartnerFragment': 'Fragment',
        'TransactionPartnerTelegramAds': 'Telegram Ads',
        'TransactionPartnerTelegramApi': 'Telegram',
        'TransactionPartnerOther': 'Telegram',
    }
    return labels.get(cls, cls.replace('TransactionPartner', '') or 'Telegram')


def _transaction_line(transaction, tz: ZoneInfo) -> str:
    amount_obj = getattr(transaction, 'amount', None)
    amount = _star_value(amount_obj)
    sign = '+' if amount > 0 else ''
    amount_text = _format_stars(amount_obj)

    raw_date = int(getattr(transaction, 'date', 0) or 0)
    if raw_date:
        dt = datetime.fromtimestamp(raw_date, tz=timezone.utc).astimezone(tz)
        date_text = dt.strftime('%d.%m %H:%M')
    else:
        date_text = '—'

    partner = getattr(transaction, 'source', None) if amount >= 0 else getattr(transaction, 'receiver', None)
    partner_text = _partner_label(partner)
    return f'• <b>{sign}{amount_text} ⭐</b> · {date_text} · {partner_text}'


def build_stars_router(ctx) -> Router:
    router = Router(name='clarify-stars-owner')
    settings = ctx.settings

    @router.message(Command('stars'))
    async def stars(message: Message):
        if not settings.admin_telegram_id or message.from_user.id != settings.admin_telegram_id:
            return await message.answer('⛔ Нет доступа.')

        try:
            balance = await ctx.bot.get_my_star_balance()
            history = await ctx.bot.get_star_transactions(limit=8)
            transactions = list(getattr(history, 'transactions', []) or [])

            tz = ZoneInfo(settings.default_timezone)
            lines = [
                '⭐ <b>Баланс Clarify</b>',
                '',
                f'На балансе бота: <b>{_format_stars(balance)} ⭐</b>',
            ]

            if transactions:
                lines += ['', '<b>Последние операции:</b>']
                lines.extend(_transaction_line(item, tz) for item in transactions[:8])
            else:
                lines += ['', 'Последних операций пока нет.']

            lines += [
                '',
                '<i>Это баланс Stars самого бота. Доступность вывода в TON Telegram рассчитывает отдельно.</i>',
            ]
            await message.answer('\n'.join(lines))
        except Exception as exc:
            await ctx.errors.record(uuid.uuid4().hex, message.from_user.id, 'stars_balance', exc)
            await message.answer(
                '⚠️ Не удалось получить баланс Stars через Telegram. '
                'Попробуй ещё раз после обновления бота.'
            )

    return router
