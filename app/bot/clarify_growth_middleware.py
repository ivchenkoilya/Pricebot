from __future__ import annotations

import logging

from aiogram import BaseMiddleware


log = logging.getLogger('clarify.growth')


class GrowthConversionMiddleware(BaseMiddleware):
    """Check conversion after a handler, when successful AI usage is already persisted."""

    def __init__(self, ctx):
        self.ctx = ctx

    async def __call__(self, handler, event, data):
        result = await handler(event, data)
        telegram_user = getattr(event, 'from_user', None)
        if telegram_user is None:
            return result

        try:
            reward = await self.ctx.growth.sync_conversion(int(telegram_user.id))
            if reward is None:
                return result

            amount = reward.amount
            await self.ctx.bot.send_message(
                reward.referred_telegram_id,
                f'🎁 <b>Реферальный бонус начислен</b>\n\n'
                f'Ты сделал первый успешный разбор в Clarify — +{amount} AI-запросов.',
            )
            await self.ctx.bot.send_message(
                reward.referrer_telegram_id,
                f'🎁 <b>Друг попробовал Clarify</b>\n\n'
                f'Его первый разбор готов. Тебе начислено +{amount} AI-запросов.',
            )
        except Exception:
            # Growth must never break the primary Clarify response path.
            log.exception('Could not sync Clarify referral conversion for telegram_id=%s', telegram_user.id)
        return result
