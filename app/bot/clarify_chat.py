from __future__ import annotations

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import Message

from app.ai.intent import classify_text_intent, looks_like_followup
from app.bot.clarify_start import ABOUT_TEXT, CAPABILITIES_TEXT, EXAMPLES_TEXT, HELP_TEXT, NO_CONTEXT_TEXT
from app.bot.razberi_helpers import get_user


GREETING_TEXT = (
    'Привет! Я <b>Clarify</b> 👋\n'
    'Отправь мне сообщение, голосовое, документ, скриншот или ссылку — помогу быстро разобраться.'
)


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

    @router.message(F.text)
    async def chat_intents(message: Message):
        text = (message.text or '').strip()
        if not text or text.startswith('/'):
            raise SkipHandler

        # Brand/help/small-talk intents are intentionally answered before any DB
        # or AI work so «Привет», «Кто ты?» and «Что умеешь?» feel instant.
        static_decision = classify_text_intent(text, False)
        if await _answer_static(message, static_decision.name):
            return

        user = await get_user(ctx, message.from_user)
        active = await ctx.conversations.recent_materials(user.id, 3)

        # Explicit follow-ups must never become a new material when /clear was used
        # or when the user has not sent anything yet.
        if not active and looks_like_followup(text):
            return await message.answer(NO_CONTEXT_TEXT)

        raise SkipHandler

    return router
