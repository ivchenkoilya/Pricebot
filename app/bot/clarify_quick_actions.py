from __future__ import annotations

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from sqlalchemy import select

from app.bot.razberi_helpers import esc, get_user
from app.bot.razberi_keyboards import (
    BTN_BACK,
    BTN_CLEAR,
    BTN_COMPARE,
    BTN_HELP,
    BTN_INBOX,
    BTN_MEMORY,
    BTN_MINIAPP,
    BTN_MORE,
    BTN_PLANS,
    BTN_PROFILE,
    BTN_PROJECTS,
    BTN_SETTINGS,
    BTN_SUPPORT,
    BTN_UNPACK,
    BTN_WRITE,
    LEGACY_CLEAR,
    LEGACY_INBOX,
    LEGACY_MEMORY,
    LEGACY_MEMORY_RU,
    LEGACY_SUPPORT,
    plans_keyboard,
    quick_webapp_url,
)
from app.bot.razberi_states import AdminSupportReply, SupportMessage
from app.database.razberi_models import Reminder
from app.services.copilot import build_inbox
from app.services.core import bonus_requests, clarify_plan


NAVIGATION_TEXTS = {
    BTN_UNPACK, BTN_WRITE, BTN_MEMORY, BTN_PROFILE, BTN_PLANS, BTN_MORE,
    BTN_INBOX, BTN_PROJECTS, BTN_COMPARE, BTN_SUPPORT, BTN_SETTINGS,
    BTN_CLEAR, BTN_HELP, BTN_MINIAPP, BTN_BACK,
    LEGACY_MEMORY, LEGACY_MEMORY_RU, LEGACY_INBOX, LEGACY_SUPPORT, LEGACY_CLEAR,
}


async def _clear_stale_input_mode(state: FSMContext) -> None:
    """A persistent menu tap must not become text for a previous FSM action."""
    current = await state.get_state()
    if not current:
        return
    protected = {SupportMessage.waiting.state, AdminSupportReply.waiting.state}
    if current not in protected:
        await state.clear()


def _plan_text(settings, current: str, bonus: int) -> str:
    extra = f' · +{bonus} доп. запросов' if bonus else ''
    return (
        '<b>💎 Тарифы Clarify</b>\n\n'
        f'Сейчас: <b>{esc(current)}</b>{extra}\n\n'
        '<b>FREE</b> — бесплатно\n'
        f'• {settings.free_daily_ai_limit} AI-запросов в день\n'
        f'• {settings.free_voice_daily_limit} голосовых в день, до {settings.free_voice_max_seconds // 60} мин\n'
        f'• документы до {settings.free_document_max_pages} страниц\n\n'
        f'<b>👑 PRO · {settings.pro_stars_price} ⭐ / 30 дней</b>\n'
        f'• до {settings.pro_daily_ai_limit} AI-запросов в день\n'
        f'• голосовые до {settings.pro_voice_max_seconds // 60} мин\n'
        f'• документы до {settings.pro_document_max_pages} страниц\n\n'
        f'<b>💎 PRO MAX · {settings.max_stars_price} ⭐ / 30 дней</b>\n'
        f'• до {settings.max_daily_ai_limit} AI-запросов в день\n'
        f'• голосовые до {settings.max_voice_max_seconds // 60} мин\n'
        f'• документы до {settings.max_document_max_pages} страниц\n\n'
        '<b>Дополнительные запросы</b>\n'
        f'• +50 — {settings.request_pack_50_stars} ⭐\n'
        f'• +150 — {settings.request_pack_150_stars} ⭐\n'
        f'• +500 — {settings.request_pack_500_stars} ⭐\n\n'
        '<i>Пакеты не сгорают и расходуются после обычного лимита тарифа.</i>'
    )


async def _send_plans(ctx, message: Message, telegram_user) -> None:
    user = await get_user(ctx, telegram_user)
    await ctx.metrics.inc('plans_open', user.id)
    await message.answer(
        _plan_text(ctx.settings, clarify_plan(user, ctx.settings), bonus_requests(user)),
        reply_markup=plans_keyboard(ctx.settings),
    )


async def _send_webapp_entry(ctx, message: Message, *, page: str, title: str, button: str) -> None:
    url = quick_webapp_url(ctx.settings.webapp_url, page)
    if not url.startswith('https://'):
        await message.answer('⚠️ Mini App сейчас не настроено. Попробуй позже.')
        return
    await message.answer(
        title,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=button, web_app=WebAppInfo(url=url)),
        ]]),
    )


def build_quick_actions_router(ctx) -> Router:
    """Reliable handlers for persistent Telegram keyboard actions.

    Telegram Android may keep reply-keyboard WebApp buttons bound to a stale
    WebView. The persistent keyboard therefore sends text, and this router
    creates a fresh inline WebApp button using the same path that works in /start.
    """
    router = Router(name='clarify-quick-actions-v2')

    @router.message(F.text.in_(NAVIGATION_TEXTS))
    async def escape_old_mode(message: Message, state: FSMContext):
        await _clear_stale_input_mode(state)
        # Continue to the concrete button handler below or to the ordinary menu
        # router. This prevents e.g. «Проекты» from becoming text for «Написать».
        raise SkipHandler

    @router.message(F.text == BTN_PLANS)
    async def plans(message: Message, state: FSMContext):
        await _clear_stale_input_mode(state)
        await _send_plans(ctx, message, message.from_user)

    @router.callback_query(F.data == 'plans:open')
    async def plans_callback(callback: CallbackQuery):
        await _send_plans(ctx, callback.message, callback.from_user)
        await callback.answer()

    @router.message(F.text.in_({BTN_INBOX, LEGACY_INBOX}))
    async def important_now(message: Message, state: FSMContext):
        await _clear_stale_input_mode(state)
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
        intro = (
            '⚡ <b>Важное сейчас</b>\n\n'
            'Здесь Clarify собирает из последних материалов <b>задачи, ближайшие сроки, риски и напоминания</b>, '
            'чтобы не искать их вручную.\n\n'
        )
        if not data['items']:
            return await message.answer(
                intro + '✅ Сейчас срочных задач, сроков или рисков не найдено.'
            )
        icons = {'task': '✅', 'deadline': '⏰', 'risk': '⚠️', 'reminder': '🔔'}
        parts = [
            intro.rstrip(),
            f"Задачи: <b>{data['tasks']}</b> · Сроки: <b>{data['deadlines']}</b> · Риски: <b>{data['risks']}</b>",
        ]
        for item in data['items'][:6]:
            parts.append(f"{icons.get(item['kind'], '•')} <b>{esc(item['title'])}</b>\n{esc(item['text'])}")
        await message.answer('\n\n'.join(parts))

    @router.message(F.text == BTN_PROFILE)
    async def profile(message: Message, state: FSMContext):
        await _clear_stale_input_mode(state)
        await _send_webapp_entry(
            ctx,
            message,
            page='profile',
            title='👤 <b>Профиль Clarify</b>\n\nОткрой профиль свежей кнопкой ниже:',
            button='👤 Открыть профиль',
        )

    @router.message(F.text == BTN_MINIAPP)
    async def miniapp(message: Message, state: FSMContext):
        await _clear_stale_input_mode(state)
        await _send_webapp_entry(
            ctx,
            message,
            page='home',
            title='🏠 <b>Clarify Mini App</b>\n\nОткрой приложение свежей кнопкой ниже:',
            button='🚀 Открыть Clarify',
        )

    return router
