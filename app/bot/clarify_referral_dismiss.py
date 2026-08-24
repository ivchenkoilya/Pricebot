from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.razberi_helpers import get_user


def build_referral_dismiss_router(ctx) -> Router:
    router = Router(name='clarify-referral-dismiss')

    @router.callback_query(F.data == 'growth:referral:dismiss')
    async def dismiss(callback: CallbackQuery):
        user = await get_user(ctx, callback.from_user)
        await ctx.growth.mark_referral_prompt_dismissed(user.id)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await callback.answer('Хорошо, буду предлагать реже')

    return router
