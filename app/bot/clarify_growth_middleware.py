from __future__ import annotations

import logging

from aiogram import BaseMiddleware
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


log = logging.getLogger('clarify.growth')


class GrowthConversionMiddleware(BaseMiddleware):
    """Sync acquisition/referrals after successful handlers without spamming CTA."""

    def __init__(self, ctx):
        self.ctx = ctx

    async def __call__(self, handler, event, data):
        telegram_user = getattr(event, 'from_user', None)
        before_successes = 0
        if telegram_user is not None:
            try:
                before_successes = await self.ctx.growth.successful_count(int(telegram_user.id))
            except Exception:
                log.exception('Could not read Clarify success count before update')

        result = await handler(event, data)
        if telegram_user is None:
            return result

        try:
            reward = await self.ctx.growth.sync_conversion(int(telegram_user.id))
            if reward is not None:
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

            # A referral CTA is considered only when THIS update actually added
            # successful AI usage. Support, payments, errors and menu taps do not
            # add AIUsage, therefore cannot trigger this prompt.
            after_successes = await self.ctx.growth.successful_count(int(telegram_user.id))
            if after_successes <= before_successes:
                return result
            if not await self.ctx.growth.referral_prompt_due(int(telegram_user.id)):
                return result

            bonus = int(self.ctx.settings.referral_bonus_requests)
            await self.ctx.bot.send_message(
                int(telegram_user.id),
                '<b>🎁 Clarify пригодился?</b>\n\n'
                f'Пригласи друга — после его первого успешного разбора вы оба получите <b>+{bonus} AI-запросов</b>.',
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text='🎁 Пригласить друга', callback_data='growth:invite'),
                ]]),
            )
        except Exception:
            # Growth must never break the primary Clarify response path.
            log.exception('Could not sync Clarify growth for telegram_id=%s', telegram_user.id)
        return result
