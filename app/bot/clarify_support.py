from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.razberi_helpers import get_user
from app.bot.razberi_states import SupportMessage
from app.services.core import is_active_pro, is_creator


SUPPORT_BUTTON = '🛟 Поддержка / сообщить об ошибке'


def _support_text(message: Message, user, settings, body: str, kind: str = 'Сообщение из бота') -> str:
    username = f'@{message.from_user.username}' if message.from_user.username else 'не указан'
    plan = 'OWNER' if is_creator(user, settings) else ('PRO' if is_active_pro(user) else 'FREE')
    return (
        f'<b>🛟 Clarify · {html.escape(kind)}</b>\n\n'
        f'<b>Пользователь:</b> <a href="tg://user?id={message.from_user.id}">{html.escape(message.from_user.first_name or "User")}</a>\n'
        f'<b>Username:</b> {html.escape(username)}\n'
        f'<b>Telegram ID:</b> <code>{message.from_user.id}</code>\n'
        f'<b>Тариф:</b> {html.escape(plan)}\n'
        f'<b>Версия:</b> {html.escape(settings.version)}\n\n'
        f'<b>Сообщение:</b>\n{html.escape((body or "").strip())}'
    )


def build_support_router(ctx) -> Router:
    router = Router(name='clarify-support')

    async def begin(message: Message, state: FSMContext):
        if not ctx.settings.admin_telegram_id:
            return await message.answer('⚠️ Поддержка пока не настроена. Попробуй позже.')
        await state.set_state(SupportMessage.waiting)
        await message.answer(
            '🛟 <b>Поддержка Clarify</b>\n\n'
            'Напиши, что произошло, что хотелось бы улучшить или какой возник вопрос.\n\n'
            'Можно также отправить <b>скриншот с подписью</b> — всё придёт владельцу Clarify напрямую в Telegram.'
        )

    @router.message(Command('support'))
    async def support_command(message: Message, state: FSMContext):
        await begin(message, state)

    @router.message(F.text == SUPPORT_BUTTON)
    async def support_button(message: Message, state: FSMContext):
        await begin(message, state)

    @router.message(SupportMessage.waiting, F.photo)
    async def support_photo(message: Message, state: FSMContext):
        admin_id = ctx.settings.admin_telegram_id
        if not admin_id:
            await state.clear()
            return await message.answer('⚠️ Поддержка пока не настроена.')
        user = await get_user(ctx, message.from_user)
        body = message.caption or 'Пользователь отправил скриншот без подписи.'
        text = _support_text(message, user, ctx.settings, body, 'Скриншот / ошибка')
        try:
            await ctx.bot.send_message(admin_id, text, parse_mode='HTML')
            await ctx.bot.send_photo(admin_id, message.photo[-1].file_id, caption=f'📎 Скриншот от {message.from_user.id}')
            await ctx.metrics.inc('support_submitted', user.id)
            await state.clear()
            await message.answer('✅ Отправлено. Владелец Clarify получил сообщение и скриншот.')
        except Exception as exc:
            await ctx.errors.record('support-bot', message.from_user.id, 'support_bot', exc)
            await message.answer('⚠️ Не получилось отправить обращение. Попробуй ещё раз.')

    @router.message(SupportMessage.waiting, F.text)
    async def support_text(message: Message, state: FSMContext):
        admin_id = ctx.settings.admin_telegram_id
        if not admin_id:
            await state.clear()
            return await message.answer('⚠️ Поддержка пока не настроена.')
        user = await get_user(ctx, message.from_user)
        text = _support_text(message, user, ctx.settings, message.text or '')
        try:
            await ctx.bot.send_message(admin_id, text, parse_mode='HTML')
            await ctx.metrics.inc('support_submitted', user.id)
            await state.clear()
            await message.answer('✅ Отправлено владельцу Clarify. Спасибо за сообщение.')
        except Exception as exc:
            await ctx.errors.record('support-bot', message.from_user.id, 'support_bot', exc)
            await message.answer('⚠️ Не получилось отправить обращение. Попробуй ещё раз.')

    @router.message(SupportMessage.waiting)
    async def support_other(message: Message):
        await message.answer('Пришли текст или скриншот с подписью — я отправлю это владельцу Clarify.')

    return router
