from __future__ import annotations

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.ai.intent import classify_text_intent, looks_like_followup
from app.bot.clarify_start import ABOUT_TEXT, CAPABILITIES_TEXT, EXAMPLES_TEXT, HELP_TEXT
from app.bot.razberi_helpers import ensure_quota, esc, get_user
from app.services.core import bonus_requests, clarify_plan


NO_CONTEXT_TEXT = (
    'Я пока не нашёл подходящий контекст.\n\n'
    'Отправь мне материал, документ, ссылку или изображение — я помогу разобраться.'
)

GREETING_TEXT = (
    'Привет! Я <b>Clarify</b> 👋\n'
    'Отправь мне сообщение, голосовое, документ, скриншот или ссылку — помогу быстро разобраться.'
)

GENERAL_QUESTION_PREFIXES = (
    'как приготовить ', 'как сделать ', 'как настроить ', 'как установить ', 'как подключить ',
    'как заменить ', 'как починить ', 'как научиться ', 'как начать ', 'как выбрать ',
    'что такое ', 'кто такой ', 'кто такая ', 'расскажи про ', 'расскажи о ',
    'объясни что такое ', 'посоветуй ', 'порекомендуй ', 'в чем разница между ', 'в чём разница между ',
)


def _clear_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='🗑 Да, удалить всё', callback_data='materials:clear:confirm'),
        InlineKeyboardButton(text='Отмена', callback_data='materials:clear:cancel'),
    ]])


def _plans_keyboard(settings=None) -> InlineKeyboardMarkup:
    if settings is None:
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='💳 Показать тарифы', callback_data='plans:open')]])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f'👑 PRO · {settings.pro_stars_price} ⭐', callback_data='plan:buy:pro')],
        [InlineKeyboardButton(text=f'💎 PRO MAX · {settings.max_stars_price} ⭐', callback_data='plan:buy:max')],
        [InlineKeyboardButton(text=f'+100 · {settings.request_pack_100_stars} ⭐', callback_data='plan:buy:pack100'), InlineKeyboardButton(text=f'+500 · {settings.request_pack_500_stars} ⭐', callback_data='plan:buy:pack500')],
        [InlineKeyboardButton(text=f'+2000 запросов · {settings.request_pack_2000_stars} ⭐', callback_data='plan:buy:pack2000')],
    ])


def _looks_like_clear_materials(text: str) -> bool:
    low = text.lower().replace('ё', 'е')
    return any(x in low for x in ('удал', 'очист', 'стер')) and any(x in low for x in ('материал', 'memory', 'памят', 'истори')) and any(x in low for x in ('все', 'всю', 'полност'))


def _looks_like_material_management(text: str) -> bool:
    low = text.lower().replace('ё', 'е')
    return any(x in low for x in ('как удалить материал', 'где удалить материал', 'очистить материалы', 'удалить материалы'))


def _looks_like_plans(text: str) -> bool:
    low = text.lower().replace('ё', 'е')
    return any(x in low for x in ('тариф', 'сколько стоит pro', 'сколько стоит подпис', 'pro max', 'докупить запрос', 'купить запрос', 'лимит запрос'))


def _looks_like_general_question(text: str, has_recent_material: bool) -> bool:
    value = ' '.join((text or '').strip().lower().split())
    if not value or len(value) > 700:
        return False
    if value.startswith(GENERAL_QUESTION_PREFIXES):
        return True
    if value.startswith(('почему вообще ', 'зачем вообще ', 'можешь объяснить ', 'можешь рассказать ')):
        return True
    # With no active material a short question is ordinary chat, not a new
    # material. If there is a recent material, ambiguous questions like
    # «когда оплатить?» are intentionally left to the context router.
    return not has_recent_material and ('?' in text or value.startswith(('почему ', 'зачем ', 'сколько ', 'где ', 'когда ', 'как ')))


async def _answer_static(message: Message, intent: str) -> bool:
    if intent == 'greeting':
        await message.answer(GREETING_TEXT); return True
    if intent == 'about':
        await message.answer(ABOUT_TEXT); return True
    if intent == 'capabilities':
        await message.answer(CAPABILITIES_TEXT); return True
    if intent == 'help':
        await message.answer(HELP_TEXT); return True
    if intent == 'examples':
        await message.answer(EXAMPLES_TEXT); return True
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

    @router.callback_query(F.data == 'plans:open')
    async def plans_open(callback: CallbackQuery):
        user = await get_user(ctx, callback.from_user)
        plan = clarify_plan(user, ctx.settings)
        extra = bonus_requests(user)
        await callback.message.answer(
            f'💳 <b>Тарифы Clarify</b>\n\nСейчас: <b>{plan}</b>' + (f' · +{extra} запросов' if extra else '') + '\n\n'
            f'<b>FREE</b> — {ctx.settings.free_daily_ai_limit} запросов/день\n'
            f'<b>PRO</b> — {ctx.settings.pro_daily_ai_limit} запросов/день · {ctx.settings.pro_stars_price} ⭐ / 30 дней\n'
            f'<b>PRO MAX</b> — {ctx.settings.max_daily_ai_limit} запросов/день · {ctx.settings.max_stars_price} ⭐ / 30 дней\n\n'
            'Можно также докупить +100, +500 или +2000 запросов. Пакеты не сгорают в конце дня.',
            reply_markup=_plans_keyboard(ctx.settings),
        )
        await callback.answer()

    @router.callback_query(F.data == 'materials:clear:ask')
    async def clear_ask(callback: CallbackQuery):
        await callback.message.answer(
            '🗑 <b>Удалить все материалы?</b>\n\nMemory очистится полностью. Проекты останутся, но удалённые материалы исчезнут из них. Это действие нельзя отменить.',
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

        # Product/navigation questions must never inherit the latest material as
        # context. This keeps Clarify behaving like a normal chatbot as well as
        # a document assistant.
        if text == '🗑 Очистить материалы' or _looks_like_clear_materials(text):
            return await message.answer(
                '🗑 <b>Можно удалить все материалы сразу.</b>\n\nЭто очистит Memory и уберёт материалы из проектов. Подтверди действие:',
                reply_markup=_clear_keyboard(),
            )
        if _looks_like_material_management(text):
            return await message.answer(
                'Один материал удаляется кнопкой <b>«Удалить»</b> внутри его карточки.\n\nЕсли хочешь очистить Memory полностью — нажми кнопку ниже.',
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
        if _looks_like_general_question(text, bool(active)):
            if not await ensure_quota(ctx, message, user):
                return
            progress = await message.answer('✨ Думаю…')
            try:
                prompt = (
                    'Ответь как обычный полезный AI-помощник Clarify. Этот вопрос НЕ нужно привязывать к сохранённым материалам. '
                    'Ответь прямо, простым разговорным языком, без канцелярита и без Markdown-символов. '
                    f'Вопрос пользователя: {text}'
                )
                answer, usage = await ctx.ai.ask(prompt, '', model=ctx.settings.fast)
                await ctx.usage.record(user.id, ctx.settings.fast, 'general_chat_question', usage)
                return await progress.edit_text(esc(answer))
            except Exception as exc:
                await ctx.errors.record('general-chat', message.from_user.id, 'general_chat_question', exc)
                return await progress.edit_text('⚠️ Не получилось ответить прямо сейчас. Попробуй ещё раз.')

        if not active and looks_like_followup(text):
            return await message.answer(NO_CONTEXT_TEXT)
        raise SkipHandler

    return router
