from __future__ import annotations

import html
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.razberi_helpers import get_user
from app.bot.razberi_states import AdminSupportReply, SupportMessage
from app.services.core import clarify_plan


SUPPORT_BUTTON = '🛟 Поддержка / сообщить об ошибке'
SUPPORT_BUTTON_SHORT = '🛟 Поддержка'
SUPPORT_WINDOW_SECONDS = 10 * 60
SUPPORT_WINDOW_LIMIT = 5
_SUPPORT_EVENTS: dict[int, deque[float]] = defaultdict(deque)


def _admin_reply_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='↩️ Ответить', callback_data=f'supportreply:{telegram_id}')
    ]])


def _user_reply_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='🛟 Написать ещё', callback_data='support:open')
    ]])


def _support_cta_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='🛟 Обратиться в поддержку', callback_data='support:open')
    ]])


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='❌ Отмена', callback_data='support:cancel')
    ]])


def _allow_support(user_id: int) -> bool:
    now = time.monotonic()
    queue = _SUPPORT_EVENTS[int(user_id)]
    while queue and now - queue[0] > SUPPORT_WINDOW_SECONDS:
        queue.popleft()
    if len(queue) >= SUPPORT_WINDOW_LIMIT:
        return False
    queue.append(now)
    return True


def _looks_like_support_intent(text: str) -> bool:
    """Conservative root-chat support intent detector.

    It intentionally does not match phrases such as "найди раздел техническая
    поддержка в документе". Active material/FSM flows are also skipped by the
    handler below so document questions keep their normal meaning.
    """
    value = re.sub(r'\s+', ' ', (text or '').strip().lower().replace('ё', 'е'))
    if not value or len(value) > 180:
        return False
    if value in {
        'поддержка', 'техподдержка', 'техническая поддержка', 'служба поддержки',
        'помощь поддержки', 'support', 'саппорт', 'баг', 'ошибка',
        'ошибка в боте', 'проблема с ботом',
    }:
        return True
    patterns = (
        r'\b(?:хочу|нужно|можно|как)\s+(?:написать|обратиться|связаться)\s+(?:в|с)?\s*поддержк',
        r'\b(?:написать|обратиться|связаться)\s+(?:в|с)?\s*поддержк',
        r'\bнаписать\s+разработчик',
        r'\bсообщить\s+(?:об\s+)?ошибк',
        r'\b(?:нашел|нашла|нашёл|есть)\s+(?:баг|ошибк)',
        r'\bбот\s+не\s+работает\b',
        r'\bпроблема\s+с\s+ботом\b',
    )
    return any(re.search(pattern, value) for pattern in patterns)


def _support_text(message: Message, user, settings, body: str, kind: str = 'Сообщение из бота') -> str:
    username = f'@{message.from_user.username}' if message.from_user.username else 'не указан'
    plan = clarify_plan(user, settings)
    created = datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')
    return (
        f'<b>🛟 Новое обращение в поддержку</b>\n\n'
        f'<b>Тип:</b> {html.escape(kind)}\n'
        f'<b>Пользователь:</b> <a href="tg://user?id={message.from_user.id}">{html.escape(message.from_user.first_name or "User")}</a>\n'
        f'<b>Username:</b> {html.escape(username)}\n'
        f'<b>Telegram ID:</b> <code>{message.from_user.id}</code>\n'
        f'<b>План:</b> {html.escape(plan)}\n'
        f'<b>Версия:</b> {html.escape(settings.version)}\n'
        f'<b>Дата:</b> {created}\n'
        f'<b>Источник:</b> Telegram-чат\n\n'
        f'<b>Сообщение:</b>\n{html.escape((body or "").strip())}'
    )


def build_support_router(ctx) -> Router:
    router = Router(name='clarify-support')

    async def begin(message: Message, state: FSMContext):
        if not ctx.settings.admin_telegram_id:
            return await message.answer('⚠️ Поддержка пока не настроена. Попробуй позже.')
        await state.set_state(SupportMessage.waiting)
        user = await get_user(ctx, message.from_user)
        await ctx.metrics.inc('support_opened', user.id)
        await message.answer(
            '🛟 <b>Поддержка Clarify</b>\n\n'
            'Опиши проблему одним сообщением. Можно отправить текст, фото, скриншот, голосовое, видео или документ.\n\n'
            '<b>Важно:</b> это обращение не будет разбираться AI, не попадёт в Memory и не потратит лимит.',
            reply_markup=_cancel_keyboard(),
        )

    async def submit_support_message(message: Message, state: FSMContext):
        admin_id = ctx.settings.admin_telegram_id
        if not admin_id:
            await state.clear()
            return await message.answer('⚠️ Поддержка пока не настроена.')
        if not _allow_support(message.from_user.id):
            return await message.answer('Слишком много сообщений подряд. Подожди немного и попробуй снова.')

        user = await get_user(ctx, message.from_user)
        media_kind = 'Сообщение'
        if message.photo:
            media_kind = 'Фото / скриншот'
        elif message.voice:
            media_kind = 'Голосовое'
        elif message.audio:
            media_kind = 'Аудио'
        elif message.document:
            media_kind = 'Документ'
        elif message.video:
            media_kind = 'Видео'
        elif message.animation:
            media_kind = 'Анимация'
        elif message.video_note:
            media_kind = 'Видеосообщение'

        body = (message.text or message.caption or '').strip()
        if not body:
            body = f'Пользователь отправил вложение: {media_kind}.'
        header = _support_text(message, user, ctx.settings, body, media_kind)
        try:
            await ctx.bot.send_message(
                admin_id,
                header,
                parse_mode='HTML',
                reply_markup=_admin_reply_keyboard(message.from_user.id),
            )
            # Text is already contained in the header. Every attachment is copied
            # verbatim, without STT, Vision, document parsing or Material creation.
            if not message.text:
                await ctx.bot.copy_message(
                    chat_id=admin_id,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id,
                )
            await ctx.metrics.inc('support_sent', user.id)
            # Old metric remains for dashboard/backward compatibility.
            await ctx.metrics.inc('support_submitted', user.id)
            await state.clear()
            await message.answer(
                '✅ <b>Сообщение отправлено в поддержку</b>\n\nСпасибо. Мы посмотрим проблему. Ответ придёт сюда же, в чат с Clarify.'
            )
        except Exception as exc:
            await ctx.errors.record('support-bot', message.from_user.id, 'support_send_failed', exc)
            await message.answer('⚠️ Не получилось отправить обращение. Попробуй ещё раз.')

    # Admin reply state has highest priority inside this router.
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
            f'↩️ <b>Ответ пользователю</b> <code>{target_id}</code>\n\n'
            'Напиши ответ одним сообщением. Для отмены — /cancel.'
        )
        await callback.answer()

    @router.message(AdminSupportReply.waiting, Command('cancel'))
    async def admin_reply_cancel(message: Message, state: FSMContext):
        if message.from_user.id != ctx.settings.admin_telegram_id:
            raise SkipHandler
        await state.clear()
        await ctx.metrics.inc('support_cancelled')
        await message.answer('❌ Ответ поддержке отменён.')

    @router.message(AdminSupportReply.waiting)
    async def admin_reply(message: Message, state: FSMContext):
        if message.from_user.id != ctx.settings.admin_telegram_id:
            raise SkipHandler
        data = await state.get_data()
        target_id = int(data.get('target_telegram_id') or 0)
        if not target_id:
            await state.clear()
            return await message.answer('⚠️ Не удалось определить получателя.')
        try:
            if message.text:
                await ctx.bot.send_message(
                    target_id,
                    '<b>🛟 Ответ поддержки Clarify</b>\n\n' + html.escape(message.text.strip()),
                    parse_mode='HTML',
                    reply_markup=_user_reply_keyboard(),
                )
            else:
                await ctx.bot.send_message(
                    target_id,
                    '<b>🛟 Ответ поддержки Clarify</b>\n\nПоддержка отправила вложение:',
                    parse_mode='HTML',
                    reply_markup=_user_reply_keyboard(),
                )
                await ctx.bot.copy_message(
                    chat_id=target_id,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id,
                )
            await ctx.metrics.inc('support_replied')
            await ctx.metrics.inc('support_replies_sent')
            await state.clear()
            await message.answer('✅ Ответ отправлен пользователю.')
        except Exception as exc:
            await ctx.errors.record('support-admin-reply', target_id, 'support_reply_failed', exc)
            await message.answer('⚠️ Не получилось отправить ответ. Возможно, пользователь заблокировал бота.')

    # While this state is active every message is support transport and must be
    # consumed here before voice/document/chat/media routers see it.
    @router.message(SupportMessage.waiting, Command('cancel'))
    async def support_cancel(message: Message, state: FSMContext):
        user = await get_user(ctx, message.from_user)
        await state.clear()
        await ctx.metrics.inc('support_cancelled', user.id)
        await message.answer('❌ Обращение отменено.')

    @router.callback_query(F.data == 'support:cancel')
    async def support_cancel_callback(callback: CallbackQuery, state: FSMContext):
        user = await get_user(ctx, callback.from_user)
        await state.clear()
        await ctx.metrics.inc('support_cancelled', user.id)
        await callback.message.answer('❌ Обращение отменено.')
        await callback.answer()

    @router.message(SupportMessage.waiting)
    async def support_any(message: Message, state: FSMContext):
        await submit_support_message(message, state)

    @router.message(Command('support'))
    async def support_command(message: Message, state: FSMContext):
        await begin(message, state)

    @router.message(F.text.in_({SUPPORT_BUTTON, SUPPORT_BUTTON_SHORT}))
    async def support_button(message: Message, state: FSMContext):
        await begin(message, state)

    @router.callback_query(F.data == 'support:open')
    async def support_callback(callback: CallbackQuery, state: FSMContext):
        if not ctx.settings.admin_telegram_id:
            await callback.answer('Поддержка пока не настроена', show_alert=True)
            return
        await state.set_state(SupportMessage.waiting)
        user = await get_user(ctx, callback.from_user)
        await ctx.metrics.inc('support_opened', user.id)
        await callback.message.answer(
            '🛟 <b>Поддержка Clarify</b>\n\n'
            'Опиши проблему одним сообщением. Можно приложить фото, голосовое, видео или документ.\n\n'
            'Обращение не будет анализироваться AI и не потратит лимит.',
            reply_markup=_cancel_keyboard(),
        )
        await callback.answer()

    # Root-chat phrases such as "поддержка" are a CTA, not AI material.
    @router.message(F.text)
    async def support_intent(message: Message, state: FSMContext):
        current_state = await state.get_state()
        if current_state:
            raise SkipHandler
        if not _looks_like_support_intent(message.text or ''):
            raise SkipHandler
        await message.answer(
            '🛟 <b>Нужна помощь?</b>\n\nНапиши нам через /support — сообщение попадёт разработчику и не будет разбираться AI.',
            reply_markup=_support_cta_keyboard(),
        )

    return router
