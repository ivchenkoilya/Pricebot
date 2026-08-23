from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from sqlalchemy import select

from app.database.models import User
from app.database.razberi_models import UserAcquisition
from app.services.core import is_active_pro, user_settings_dict


AUDIENCE_LABELS = {
    'all': 'Все пользователи Clarify',
    'active30': 'Активные за 30 дней',
    'free': 'Только FREE',
    'pro': 'Только PRO / MAX',
}

_RUNNING_BROADCASTS: set[asyncio.Task] = set()


class BroadcastState(StatesGroup):
    waiting_message = State()
    waiting_confirm = State()


def _is_admin(ctx, telegram_id: int) -> bool:
    return bool(ctx.settings.admin_telegram_id and int(telegram_id) == int(ctx.settings.admin_telegram_id))


def _marketing_enabled(user: User) -> bool:
    return user_settings_dict(user).get('clarify_marketing_enabled', True) is not False


def _audience_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='👥 Всем', callback_data='broadcast:audience:all')],
            [InlineKeyboardButton(text='🟢 Активным за 30 дней', callback_data='broadcast:audience:active30')],
            [
                InlineKeyboardButton(text='🆓 Только FREE', callback_data='broadcast:audience:free'),
                InlineKeyboardButton(text='👑 PRO / MAX', callback_data='broadcast:audience:pro'),
            ],
            [InlineKeyboardButton(text='✖️ Отмена', callback_data='broadcast:cancel')],
        ]
    )


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='🚀 Запустить рассылку', callback_data='broadcast:confirm')],
            [InlineKeyboardButton(text='✖️ Отмена', callback_data='broadcast:cancel')],
        ]
    )


def _preferences_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    if enabled:
        button = InlineKeyboardButton(text='🔕 Отключить акции и новости', callback_data='broadcast:prefs:off')
    else:
        button = InlineKeyboardButton(text='🔔 Включить акции и новости', callback_data='broadcast:prefs:on')
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


def _recipient_keyboard(ctx) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    webapp_url = (ctx.settings.webapp_url or '').strip()
    if webapp_url.startswith('https://'):
        rows.append([InlineKeyboardButton(text='🚀 Открыть Clarify', web_app=WebAppInfo(url=webapp_url))])
    rows.append(
        [InlineKeyboardButton(text='🔕 Не получать такие сообщения', callback_data='broadcast:unsubscribe')]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _set_marketing_enabled(ctx, telegram_id: int, enabled: bool) -> bool:
    async with ctx.db.sessions() as session:
        user = (
            await session.execute(select(User).where(User.telegram_id == int(telegram_id)))
        ).scalar_one_or_none()
        if user is None:
            return False
        data = user_settings_dict(user)
        data['clarify_marketing_enabled'] = bool(enabled)
        user.notification_settings = json.dumps(data, ensure_ascii=False)
        await session.commit()
        return True


async def _recipient_ids(ctx, audience: str) -> list[int]:
    cutoff = datetime.utcnow() - timedelta(days=30)
    async with ctx.db.sessions() as session:
        stmt = (
            select(User)
            .join(UserAcquisition, UserAcquisition.user_id == User.id)
            .order_by(User.id)
        )
        if audience == 'active30':
            stmt = stmt.where(User.last_active_at >= cutoff)
        users = list((await session.execute(stmt)).scalars().all())

    result: list[int] = []
    for user in users:
        if _is_admin(ctx, user.telegram_id):
            continue
        if not _marketing_enabled(user):
            continue

        pro = is_active_pro(user)
        if audience == 'free' and pro:
            continue
        if audience == 'pro' and not pro:
            continue
        result.append(int(user.telegram_id))
    return result


async def _send_broadcast(
    ctx,
    *,
    admin_chat_id: int,
    source_chat_id: int,
    source_message_id: int,
    audience: str,
) -> None:
    bot: Bot = ctx.bot
    recipients = await _recipient_ids(ctx, audience)
    sent = 0
    blocked = 0
    failed = 0
    keyboard = _recipient_keyboard(ctx)

    for telegram_id in recipients:
        while True:
            try:
                await bot.copy_message(
                    chat_id=telegram_id,
                    from_chat_id=source_chat_id,
                    message_id=source_message_id,
                    reply_markup=keyboard,
                )
                sent += 1
                break
            except TelegramRetryAfter as exc:
                await asyncio.sleep(float(exc.retry_after) + 0.25)
                continue
            except TelegramForbiddenError:
                blocked += 1
                break
            except TelegramBadRequest:
                failed += 1
                break
            except Exception as exc:
                failed += 1
                try:
                    await ctx.errors.record(
                        f'broadcast-{source_message_id}',
                        telegram_id,
                        'broadcast_send',
                        exc,
                    )
                except Exception:
                    pass
                break
        # Stay below Telegram's normal broadcast ceiling and leave headroom for
        # ordinary bot replies.
        await asyncio.sleep(0.05)

    try:
        if sent:
            await ctx.metrics.inc('broadcast_sent', value=sent)
        if blocked:
            await ctx.metrics.inc('broadcast_blocked', value=blocked)
        if failed:
            await ctx.metrics.inc('broadcast_failed', value=failed)
    except Exception:
        pass

    total = len(recipients)
    label = AUDIENCE_LABELS.get(audience, audience)
    await bot.send_message(
        admin_chat_id,
        '<b>📢 Рассылка завершена</b>\n\n'
        f'Аудитория: <b>{label}</b>\n'
        f'Получателей: <b>{total}</b>\n'
        f'✅ Отправлено: <b>{sent}</b>\n'
        f'🚫 Заблокировали бота: <b>{blocked}</b>\n'
        f'⚠️ Ошибок: <b>{failed}</b>',
    )


def build_broadcast_router(ctx) -> Router:
    router = Router(name='clarify-broadcast')

    @router.message(Command('broadcast'))
    async def broadcast_command(message: Message, state: FSMContext):
        if not _is_admin(ctx, message.from_user.id):
            return
        await state.clear()
        await message.answer(
            '<b>📢 Новая рассылка</b>\n\n'
            'Выбери, кому отправить сообщение. В рассылку попадают только пользователи Clarify, '
            'которые не отключили акции и новости.',
            reply_markup=_audience_keyboard(),
        )

    @router.callback_query(F.data.startswith('broadcast:audience:'))
    async def choose_audience(callback: CallbackQuery, state: FSMContext):
        if not _is_admin(ctx, callback.from_user.id):
            return await callback.answer('Нет доступа', show_alert=True)

        audience = callback.data.rsplit(':', 1)[-1]
        if audience not in AUDIENCE_LABELS:
            return await callback.answer('Неизвестная аудитория', show_alert=True)

        await state.clear()
        await state.update_data(audience=audience)
        await state.set_state(BroadcastState.waiting_message)
        await callback.message.answer(
            f'<b>{AUDIENCE_LABELS[audience]}</b>\n\n'
            'Теперь пришли <b>одно готовое сообщение</b>, которое нужно разослать. '
            'Можно отправить текст, фото, видео, документ, голосовое или сообщение с подписью.\n\n'
            'Я сначала покажу предпросмотр и попрошу подтверждение.'
        )
        await callback.answer()

    @router.message(BroadcastState.waiting_message)
    async def capture_broadcast_message(message: Message, state: FSMContext, bot: Bot):
        if not _is_admin(ctx, message.from_user.id):
            await state.clear()
            return

        try:
            await bot.copy_message(
                chat_id=message.chat.id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
        except Exception:
            return await message.answer(
                'Не получилось скопировать этот тип сообщения. '
                'Пришли обычный текст, фото, видео, документ или голосовое.'
            )

        data = await state.get_data()
        audience = data.get('audience', 'all')
        recipients = await _recipient_ids(ctx, audience)
        await state.update_data(
            source_chat_id=message.chat.id,
            source_message_id=message.message_id,
        )
        await state.set_state(BroadcastState.waiting_confirm)

        await message.answer(
            '<b>Предпросмотр выше.</b>\n\n'
            f'Аудитория: <b>{AUDIENCE_LABELS.get(audience, audience)}</b>\n'
            f'Сейчас получателей: <b>{len(recipients)}</b>\n\n'
            'После запуска сообщение будет отправляться постепенно, чтобы Telegram не ограничил бота.',
            reply_markup=_confirm_keyboard(),
        )

    @router.callback_query(F.data == 'broadcast:confirm')
    async def confirm_broadcast(callback: CallbackQuery, state: FSMContext):
        if not _is_admin(ctx, callback.from_user.id):
            return await callback.answer('Нет доступа', show_alert=True)

        data = await state.get_data()
        audience = data.get('audience')
        source_chat_id = data.get('source_chat_id')
        source_message_id = data.get('source_message_id')
        if audience not in AUDIENCE_LABELS or not source_chat_id or not source_message_id:
            await state.clear()
            await callback.message.answer('Данные рассылки потерялись. Запусти /broadcast ещё раз.')
            return await callback.answer()

        await state.clear()
        task = asyncio.create_task(
            _send_broadcast(
                ctx,
                admin_chat_id=callback.message.chat.id,
                source_chat_id=int(source_chat_id),
                source_message_id=int(source_message_id),
                audience=str(audience),
            ),
            name=f'broadcast-{source_message_id}',
        )
        _RUNNING_BROADCASTS.add(task)
        task.add_done_callback(_RUNNING_BROADCASTS.discard)

        count = len(await _recipient_ids(ctx, str(audience)))
        await callback.message.answer(
            f'🚀 <b>Рассылка запущена</b>\n\n'
            f'Получателей: <b>{count}</b>.\n'
            'Можно продолжать пользоваться ботом — итоговая статистика придёт отдельным сообщением.'
        )
        await callback.answer('Рассылка запущена')

    @router.callback_query(F.data == 'broadcast:cancel')
    async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):
        if not _is_admin(ctx, callback.from_user.id):
            return await callback.answer('Нет доступа', show_alert=True)
        await state.clear()
        await callback.message.answer('Рассылка отменена.')
        await callback.answer()

    @router.callback_query(F.data == 'broadcast:unsubscribe')
    async def unsubscribe(callback: CallbackQuery):
        changed = await _set_marketing_enabled(ctx, callback.from_user.id, False)
        if changed:
            await callback.answer('Акции и новости отключены', show_alert=True)
        else:
            await callback.answer('Не удалось изменить настройку', show_alert=True)

    @router.message(Command('notifications'))
    async def notification_preferences(message: Message):
        user = await ctx.users.upsert(message.from_user)
        enabled = _marketing_enabled(user)
        status = 'включены' if enabled else 'отключены'
        await message.answer(
            '<b>🔔 Рассылки Clarify</b>\n\n'
            f'Акции, промокоды и новости сейчас <b>{status}</b>.\n'
            'Системные сообщения о платежах и важных действиях эта настройка не отключает.',
            reply_markup=_preferences_keyboard(enabled),
        )

    @router.callback_query(F.data.startswith('broadcast:prefs:'))
    async def change_preferences(callback: CallbackQuery):
        enabled = callback.data.endswith(':on')
        changed = await _set_marketing_enabled(ctx, callback.from_user.id, enabled)
        if not changed:
            return await callback.answer('Не удалось изменить настройку', show_alert=True)

        status = 'включены' if enabled else 'отключены'
        try:
            await callback.message.edit_text(
                '<b>🔔 Рассылки Clarify</b>\n\n'
                f'Акции, промокоды и новости сейчас <b>{status}</b>.\n'
                'Системные сообщения о платежах и важных действиях эта настройка не отключает.',
                reply_markup=_preferences_keyboard(enabled),
            )
        except TelegramBadRequest:
            pass
        await callback.answer('Настройка сохранена')

    return router
