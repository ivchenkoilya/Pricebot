from __future__ import annotations

import uuid

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from sqlalchemy import select

from app.bot.clarify_start import HELP_TEXT
from app.bot.razberi_helpers import ensure_quota, esc, get_user
from app.bot.razberi_keyboards import (
    BTN_CLEAR,
    BTN_COMPARE,
    BTN_HELP,
    BTN_INBOX,
    BTN_MEMORY,
    BTN_MINIAPP,
    BTN_PLANS,
    BTN_PROJECTS,
    BTN_SETTINGS,
    BTN_SUPPORT,
    BTN_UNPACK,
    BTN_WRITE,
    LEGACY_CLEAR,
    LEGACY_INBOX,
    LEGACY_MEMORY,
    LEGACY_SUPPORT,
    draft_actions,
    materials_list,
    plans_keyboard,
    projects_list,
    quick_webapp_url,
)
from app.bot.razberi_states import CompareMaterials, SupportMessage, WriteForMe
from app.database.razberi_models import Reminder
from app.services.copilot import build_inbox
from app.services.core import bonus_requests, clarify_plan


def build_menu_router(ctx) -> Router:
    """Single source of truth for all persistent Telegram menu actions."""
    router = Router(name='clarify-main-menu')
    settings = ctx.settings

    @router.message(F.text == BTN_UNPACK)
    async def unpack(message: Message):
        await message.answer(
            '📎 <b>Отправь материал</b>\n\n'
            'Голосовое, аудио, документ, скриншот, фото, ссылку или обычный текст. '
            'Clarify сам определит формат и предложит полезные действия.'
        )

    @router.message(F.text == BTN_WRITE)
    async def write(message: Message, state: FSMContext):
        await state.set_state(WriteForMe.waiting)
        await message.answer(
            '✍️ <b>Что написать за тебя?</b>\n\n'
            'Опиши смысл как получится. Например: «поставщику — товар нужен к пятнице, спроси, успеет ли он». '
            'Я превращу это в готовое сообщение.'
        )

    @router.message(WriteForMe.waiting, F.text)
    async def write_for_me(message: Message, state: FSMContext):
        user = await get_user(ctx, message.from_user)
        if not await ensure_quota(ctx, message, user):
            return
        progress = await message.answer('✍️ Пишу…')
        try:
            style = await ctx.styles.get(user.id)
            raw, usage = await ctx.ai.compose(message.text or '', style)
            await ctx.usage.record(user.id, settings.fast, 'compose', usage)
            material = await ctx.materials.create(user.id, 'draft', 'Черновик сообщения', raw, raw)
            await state.clear()
            await progress.edit_text(
                '✍️ <b>Готовый текст</b>\n\n' + esc(raw),
                reply_markup=draft_actions(material.id),
            )
        except Exception as exc:
            await state.clear()
            await ctx.errors.record(uuid.uuid4().hex, message.from_user.id, 'compose', exc)
            await progress.edit_text('⚠️ Не получилось написать текст. Попробуй ещё раз.')

    @router.message(F.text.in_({BTN_MEMORY, LEGACY_MEMORY}))
    async def memory(message: Message):
        user = await get_user(ctx, message.from_user)
        items = await ctx.materials.latest(user.id, 10)
        if not items:
            return await message.answer(
                '🧠 <b>Memory пока пустая.</b>\n\nОтправь первый материал — Clarify сохранит его сюда.'
            )
        await message.answer(
            '🧠 <b>Memory</b>\n\nПоследние материалы. Можно открыть любой или написать мне прямо в чат: '
            '«найди в памяти, где было про оплату».',
            reply_markup=materials_list(items),
        )

    @router.message(F.text.in_({BTN_INBOX, LEGACY_INBOX}))
    async def inbox(message: Message):
        user = await get_user(ctx, message.from_user)
        materials = await ctx.materials.latest(user.id, 24)
        async with ctx.db.sessions() as db:
            reminders = list((await db.execute(
                select(Reminder)
                .where(Reminder.user_id == user.id, Reminder.status == 'active')
                .order_by(Reminder.remind_at.asc())
                .limit(10)
            )).scalars())
        data = build_inbox(materials, reminders, limit=6)
        if not data['items']:
            return await message.answer(
                '⚡ <b>Важное сейчас</b>\n\n'
                'Здесь Clarify собирает задачи, ближайшие сроки, риски и напоминания из последних материалов.\n\n'
                '✅ Сейчас срочных пунктов не найдено.'
            )
        icons = {'task': '✅', 'deadline': '⏰', 'risk': '⚠️', 'reminder': '🔔'}
        parts = [
            '⚡ <b>Важное сейчас</b>',
            'Здесь Clarify собирает задачи, ближайшие сроки, риски и напоминания из последних материалов.',
            f"✅ Задачи: <b>{data['tasks']}</b> · ⏰ Сроки: <b>{data['deadlines']}</b> · ⚠️ Риски: <b>{data['risks']}</b>",
        ]
        for item in data['items'][:6]:
            parts.append(
                f"{icons.get(item['kind'], '•')} <b>{esc(item['title'])}</b>\n{esc(item['text'])}"
            )
        await message.answer('\n\n'.join(parts))

    @router.message(F.text == BTN_PROJECTS)
    async def projects(message: Message):
        user = await get_user(ctx, message.from_user)
        items = await ctx.projects.list(user.id)
        if not items:
            return await message.answer(
                '📁 <b>Проектов пока нет.</b>\n\nСоздай первый проект и собирай связанные материалы в одну тему.',
                reply_markup=projects_list([]),
            )
        await message.answer(
            '📁 <b>Проекты</b>\n\nОткрой проект или создай новый:',
            reply_markup=projects_list(items),
        )

    @router.message(F.text == BTN_COMPARE)
    async def compare(message: Message, state: FSMContext):
        user = await get_user(ctx, message.from_user)
        items = await ctx.materials.latest(user.id, 10)
        if len(items) < 2:
            return await message.answer('🔀 Для сравнения нужно хотя бы два материала в Memory.')
        await state.set_state(CompareMaterials.waiting_ids)
        await message.answer(
            '🔀 <b>Сравнить материалы</b>\n\n'
            'Пришли два номера одним сообщением, например <code>12 15</code>. '
            'Clarify сравнит отличия, деньги, сроки, обязательства и риски.',
            reply_markup=materials_list(items),
        )

    @router.message(F.text == BTN_PLANS)
    async def plans(message: Message):
        user = await get_user(ctx, message.from_user)
        plan = clarify_plan(user, settings)
        extra = bonus_requests(user)
        current = f'Текущий тариф: <b>{plan}</b>'
        if extra:
            current += f' · бонус <b>+{extra}</b>'

        await message.answer(
            '💎 <b>Тарифы Clarify</b>\n'
            f'{current}\n\n'
            '🆓 <b>FREE</b>\n'
            f'• <b>{settings.free_daily_ai_limit}</b> AI-запросов в день\n'
            f'• <b>{settings.free_voice_daily_limit}</b> голосовых в день, до <b>{settings.free_voice_max_seconds // 60} мин</b> каждое\n'
            f'• документы до <b>{settings.free_document_max_pages} страниц</b>\n\n'
            f'👑 <b>PRO · {settings.pro_stars_price} ⭐ / 30 дней</b>\n'
            f'• <b>{settings.pro_daily_ai_limit}</b> AI-запросов в день\n'
            f'• голосовые, аудио и видео до <b>{settings.pro_voice_max_seconds // 60} мин</b>\n'
            f'• документы до <b>{settings.pro_document_max_pages} страниц</b>\n\n'
            f'💎 <b>PRO MAX · {settings.max_stars_price} ⭐ / 30 дней</b>\n'
            f'• <b>{settings.max_daily_ai_limit}</b> AI-запросов в день\n'
            f'• голосовые, аудио и видео до <b>{settings.max_voice_max_seconds // 60} мин</b>\n'
            f'• документы до <b>{settings.max_document_max_pages} страниц</b>\n\n'
            '➕ <b>Дополнительные запросы</b>\n'
            f'• +50 — <b>{settings.request_pack_50_stars} ⭐</b>\n'
            f'• +150 — <b>{settings.request_pack_150_stars} ⭐</b>\n'
            f'• +500 — <b>{settings.request_pack_500_stars} ⭐</b>\n\n'
            '<i>Пакеты не сгорают и расходуются только после обычного лимита тарифа.</i>',
            reply_markup=plans_keyboard(settings),
        )

    @router.message(F.text.in_({BTN_SUPPORT, LEGACY_SUPPORT}))
    async def support(message: Message, state: FSMContext):
        if not settings.admin_telegram_id:
            return await message.answer('⚠️ Поддержка пока не настроена. Попробуй позже.')
        await state.set_state(SupportMessage.waiting)
        await message.answer(
            '🛟 <b>Поддержка Clarify</b>\n\n'
            'Напиши вопрос, идею или опиши ошибку. Можно отправить скриншот с подписью. '
            'Ответ поддержки придёт сюда же.'
        )

    @router.message(F.text == BTN_SETTINGS)
    async def settings_view(message: Message):
        user = await get_user(ctx, message.from_user)
        style = await ctx.styles.get(user.id)
        plan = clarify_plan(user, settings)
        await message.answer(
            '⚙️ <b>Настройки Clarify</b>\n\n'
            f'Часовой пояс: <b>{esc(user.timezone or settings.default_timezone)}</b>\n'
            f'Тариф: <b>{plan}</b>\n'
            f'AI режим по умолчанию: <b>{"Smart" if plan in {"PRO", "MAX", "OWNER"} else "Fast"}</b>\n'
            f'Стиль ответов: <b>{"настроен ✅" if style else "по умолчанию"}</b>\n\n'
            'Чтобы настроить свой стиль для сообщений, используй /style. Расширенные настройки доступны в Mini App.'
        )

    @router.message(F.text.in_({BTN_CLEAR, LEGACY_CLEAR}))
    async def clear_materials(message: Message):
        await message.answer(
            '🗑 <b>Очистить всю Memory?</b>\n\n'
            'Будут удалены все сохранённые материалы и их связи с проектами. Тариф и настройки останутся. '
            'Это действие нельзя отменить.',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                text='🗑 Да, удалить всё', callback_data='materials:clear:confirm'
            ), InlineKeyboardButton(text='Отмена', callback_data='materials:clear:cancel')]]),
        )

    @router.message(F.text == BTN_HELP)
    async def help_button(message: Message):
        await message.answer(HELP_TEXT)

    @router.message(F.text == BTN_MINIAPP)
    async def miniapp_fallback(message: Message):
        url = quick_webapp_url(settings.webapp_url, 'home')
        if url.startswith('https://'):
            return await message.answer(
                '🏠 <b>Clarify Mini App</b>\n\nНажми свежую кнопку ниже, чтобы открыть приложение:',
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text='🚀 Открыть Mini App', web_app=WebAppInfo(url=url))
                ]]),
            )
        await message.answer('⚠️ Mini App сейчас не настроено. Попробуй позже.')

    return router
