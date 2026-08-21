from __future__ import annotations

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.ai.intent import classify_text_intent, looks_like_followup
from app.bot.clarify_start import ABOUT_TEXT, CAPABILITIES_TEXT, EXAMPLES_TEXT, HELP_TEXT
from app.bot.razberi_helpers import get_user
from app.services.core import bonus_requests, clarify_plan


NO_CONTEXT_TEXT = (
    'Я пока не нашёл подходящий контекст.\n\n'
    'Отправь мне материал, документ, ссылку или изображение — я помогу разобраться.'
)


GREETING_TEXT = (
    'Привет! Я <b>Clarify</b> 👋\n'
    'Отправь мне сообщение, голосовое, документ, скриншот или ссылку — помогу быстро разобраться.'
)


def _clear_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='🗑 Да, удалить всё', callback_data='materials:clear:confirm'),
        InlineKeyboardButton(text='Отмена', callback_data='materials:clear:cancel'),
    ]])


def _plans_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='💳 Показать тарифы', callback_data='plans:open')]])


def _looks_like_clear_materials(text: str) -> bool:
    low = text.lower().replace('ё', 'е')
    delete_words = ('удал', 'очист', 'стер')
    material_words = ('материал', 'memory', 'памят', 'истори')
    all_words = ('все', 'всю', 'полност')
    return any(x in low for x in delete_words) and any(x in low for x in material_words) and any(x in low for x in all_words)


def _looks_like_material_management(text: str) -> bool:
    low = text.lower().replace('ё', 'е')
    return any(x in low for x in ('как удалить материал', 'где удалить материал', 'очистить материалы', 'удалить материалы'))


def _looks_like_plans(text: str) -> bool:
    low = text.lower().replace('ё', 'е')
    return any(x in low for x in ('тариф', 'сколько стоит pro', 'сколько стоит подпис', 'pro max', 'докупить запрос', 'купить запрос', 'лимит запрос'))


async def _answer_static(message: Message, intent: str) -> bool:
    if intent == 'greeting':
        await message.answer(GREETING_TEXT)
        return True
    if intent == 'about':
        await message.answer(ABOUT_TEXT)
        return True
    if intent == 'capabilities':
        await message.answer(CAPABILITIES_TEXT)
        return True
    if intent == 'help':
        await message.answer(HELP_TEXT)
        return True
    if intent == 'examples':
        await message.answer(EXAMPLES_TEXT)
        return True
    if intent == 'general_chat':
        low = (message.text or '').strip().lower()
        if any(word in low for word in ('спасибо', 'спс', 'благодарю')):
            await message.answer('Пожалуйста 🙂 Если есть ещё материал — отправляй, разберём.')
        elif low in {'понял', 'понятно'}:
            await message.answer('Отлично. Если что-то останется непонятным — просто спроси.')
        else:
            await message.answer('Всё отлично — готов разбираться в информации 😄 Что посмотрим?')
        return True
    return False


def build_chat_router(ctx) -> Router:
    router = Router(name='clarify-chat')

    @router.callback_query(F.data == 'materials:clear:ask')
    async def clear_ask(callback: CallbackQuery):
        await callback.message.answer(
            '🗑 <b>Удалить все материалы?</b>\n\n'
            'Memory очистится полностью. Проекты останутся, но удалённые материалы исчезнут из них. Это действие нельзя отменить.',
            reply_markup=_clear_keyboard(),
        )
        await callback.answer()

    @router.callback_query(F.data == 'materials:clear:cancel')
    async def clear_cancel(callback: CallbackQuery):
        await callback.answer('Отменено')
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

    @router.callback_query(F.data == 'materials:clear:confirm')
    async def clear_confirm(callback: CallbackQuery):
        user = await get_user(ctx, callback.from_user)
        count = await ctx.materials.delete_user_materials(user.id)
        await ctx.conversations.clear(user.id)
        await ctx.metrics.inc('materials_cleared', user.id, max(1, count))
        await callback.message.answer(f'✅ Memory очищена. Удалено материалов: <b>{count}</b>.')
        await callback.answer('Готово')

    @router.message(F.text)
    async def chat_intents(message: Message):
        text = (message.text or '').strip()
        if not text or text.startswith('/'):
            raise SkipHandler

        # Questions about Clarify itself must never be answered from the last
        # uploaded material. Handle product/navigation intents before context QA.
        if text == '🗑 Очистить материалы' or _looks_like_clear_materials(text):
            return await message.answer(
                '🗑 <b>Можно удалить все материалы сразу.</b>\n\n'
                'Это очистит Memory и уберёт материалы из проектов. Подтверди действие:',
                reply_markup=_clear_keyboard(),
            )
        if _looks_like_material_management(text):
            return await message.answer(
                'Один материал удаляется кнопкой <b>«Удалить»</b> внутри его карточки.\n\n'
                'Если хочешь очистить Memory полностью — нажми кнопку ниже.',
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🗑 Удалить все материалы', callback_data='materials:clear:ask')]]),
            )
        if _looks_like_plans(text):
            user = await get_user(ctx, message.from_user)
            plan = clarify_plan(user, ctx.settings)
            extra = bonus_requests(user)
            return await message.answer(
                f'💳 <b>Тарифы Clarify</b>\n\nСейчас у тебя: <b>{plan}</b>' + (f' · +{extra} запросов' if extra else '') + '\n\n'
                f'FREE — {ctx.settings.free_daily_ai_limit} запросов/день\n'
                f'PRO — {ctx.settings.pro_daily_ai_limit} запросов/день · {ctx.settings.pro_stars_price} ⭐\n'
                f'PRO MAX — {ctx.settings.max_daily_ai_limit} запросов/день · {ctx.settings.max_stars_price} ⭐\n\n'
                'Также можно отдельно докупить +100, +500 или +2000 запросов.',
                reply_markup=_plans_keyboard(),
            )

        static_decision = classify_text_intent(text, False)
        if await _answer_static(message, static_decision.name):
            return

        user = await get_user(ctx, message.from_user)
        active = await ctx.conversations.recent_materials(user.id, 3)

        if not active and looks_like_followup(text):
            return await message.answer(NO_CONTEXT_TEXT)

        raise SkipHandler

    return router
