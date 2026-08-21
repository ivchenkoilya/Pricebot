from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.razberi_helpers import get_user
from app.bot.razberi_states import AdminSupportReply, SupportMessage
from app.services.core import is_active_pro, is_creator


SUPPORT_BUTTON = '🛟 Поддержка / сообщить об ошибке'


def _admin_reply_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='💬 Ответить пользователю', callback_data=f'supportreply:{telegram_id}')
    ]])


def _user_reply_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='↩️ Ответить поддержке', callback_data='support:open')
    ]])


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
            'Можно также отправить <b>скриншот с подписью</b>. Ответ поддержки придёт сюда же, в этот чат.'
        )

    @router.message(Command('support'))
    async def support_command(message: Message, state: FSMContext):
        await begin(message, state)

    @router.message(F.text == SUPPORT_BUTTON)
    async def support_button(message: Message, state: FSMContext):
        await begin(message, state)

    @router.callback_query(F.data == 'support:open')
    async def support_callback(callback: CallbackQuery, state: FSMContext):
        if not ctx.settings.admin_telegram_id:
            await callback.answer('Поддержка пока не настроена', show_alert=True)
            return
        await state.set_state(SupportMessage.waiting)
        await callback.message.answer(
            '🛟 <b>Поддержка Clarify</b>\n\n'
            'Напиши ответ, вопрос, идею или опиши ошибку. Можно приложить скриншот с подписью. '
            'Ответ поддержки придёт сюда же.'
        )
        await callback.answer()

    @router.callback_query(F.data.startswith('supportreply:'))
    async def admin_reply_begin(callback: CallbackQuery, state: FSMContext):
        admin_id = ctx.settings.admin_telegram_id
        if not admin_id or callback.from_user.id != admin_id:
            return await callback.answer('Эта кнопка доступна только владельцу Clarify', show_alert=True)
        try:
            target_id = int(callback.data.split(':', 1)[1])
        except (ValueError, IndexError):
            return await callback.answer('Не удалось определить пользователя', show_alert=True)
        await state.set_state(AdminSupportReply.waiting)
        await state.update_data(target_telegram_id=target_id)
        await callback.message.answer(
            f'💬 <b>Ответ пользователю</b> <code>{target_id}</code>\n\n'
            'Напиши ответ одним сообщением. Можно отправить текст или фото с подписью.\n'
            'Для отмены — /cancel.'
        )
        await callback.answer()

    @router.message(AdminSupportReply.waiting, Command('cancel'))
    async def admin_reply_cancel(message: Message, state: FSMContext):
        if message.from_user.id != ctx.settings.admin_telegram_id:
            return
        await state.clear()
        await message.answer('❌ Ответ поддержке отменён.')

    @router.message(AdminSupportReply.waiting, F.photo)
    async def admin_reply_photo(message: Message, state: FSMContext):
        if message.from_user.id != ctx.settings.admin_telegram_id:
            return
        data = await state.get_data()
        target_id = int(data.get('target_telegram_id') or 0)
        if not target_id:
            await state.clear()
            return await message.answer('⚠️ Не удалось определить получателя.')
        caption = (message.caption or '').strip()
        user_caption = '<b>💬 Ответ поддержки Clarify</b>'
        if caption:
            user_caption += '\n\n' + html.escape(caption)
        try:
            await ctx.bot.send_photo(
                target_id,
                message.photo[-1].file_id,
                caption=user_caption,
                parse_mode='HTML',
                reply_markup=_user_reply_keyboard(),
            )
            await ctx.metrics.inc('support_replies_sent')
            await state.clear()
            await message.answer('✅ Ответ и фото отправлены пользователю.')
        except Exception as exc:
            await ctx.errors.record('support-admin-reply', target_id, 'support_admin_reply', exc)
            await message.answer('⚠️ Не получилось отправить ответ. Возможно, пользователь заблокировал бота.')

    @router.message(AdminSupportReply.waiting, F.text)
    async def admin_reply_text(message: Message, state: FSMContext):
        if message.from_user.id != ctx.settings.admin_telegram_id:
            return
        data = await state.get_data()
        target_id = int(data.get('target_telegram_id') or 0)
        if not target_id:
            await state.clear()
            return await message.answer('⚠️ Не удалось определить получателя.')
        try:
            await ctx.bot.send_message(
                target_id,
                '<b>💬 Ответ поддержки Clarify</b>\n\n' + html.escape((message.text or '').strip()),
                parse_mode='HTML',
                reply_markup=_user_reply_keyboard(),
            )
            await ctx.metrics.inc('support_replies_sent')
            await state.clear()
            await message.answer('✅ Ответ отправлен пользователю.')
        except Exception as exc:
            await ctx.errors.record('support-admin-reply', target_id, 'support_admin_reply', exc)
            await message.answer('⚠️ Не получилось отправить ответ. Возможно, пользователь заблокировал бота.')

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
            await ctx.bot.send_message(
                admin_id,
                text,
                parse_mode='HTML',
                reply_markup=_admin_reply_keyboard(message.from_user.id),
            )
            await ctx.bot.send_photo(admin_id, message.photo[-1].file_id, caption=f'📎 Скриншот от {message.from_user.id}')
            await ctx.metrics.inc('support_submitted', user.id)
            await state.clear()
            await message.answer('✅ Отправлено. Поддержка получила сообщение. Ответ придёт сюда же.')
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
            await ctx.bot.send_message(
                admin_id,
                text,
                parse_mode='HTML',
                reply_markup=_admin_reply_keyboard(message.from_user.id),
            )
            await ctx.metrics.inc('support_submitted', user.id)
            await state.clear()
            await message.answer('✅ Отправлено поддержке. Ответ придёт сюда же, в Clarify.')
        except Exception as exc:
            await ctx.errors.record('support-bot', message.from_user.id, 'support_bot', exc)
            await message.answer('⚠️ Не получилось отправить обращение. Попробуй ещё раз.')

    @router.message(SupportMessage.waiting)
    async def support_other(message: Message):
        await message.answer('Пришли текст или скриншот с подписью — я отправлю это поддержке Clarify.')

    return router
