from __future__ import annotations

import html

from aiogram.types import Message

from app.bot.razberi_keyboards import pro_button


def esc(value) -> str:
    return html.escape(str(value or ''))


async def get_user(ctx, telegram_user):
    return await ctx.users.upsert(telegram_user)


async def ensure_quota(ctx, message: Message, user, feature: str = 'ai') -> bool:
    if await ctx.usage.allowed(user, feature):
        return True
    await ctx.metrics.inc('free_limit_reached', user.id)
    await message.answer(
        'Лимит AI на сегодня закончился. 👑 PRO даёт больше обработок.',
        reply_markup=pro_button(),
    )
    return False


async def send_long_text(message: Message, text: str, *, limit: int = 12000) -> None:
    source = text or ''
    for start in range(0, min(len(source), limit), 3800):
        await message.answer('<pre>' + esc(source[start:start + 3800]) + '</pre>')
    if len(source) > limit:
        await message.answer(f'…показаны первые {limit:,} символов.'.replace(',', ' '))
