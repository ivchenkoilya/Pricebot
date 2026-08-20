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


def build_chat_router(ctx) -> Router:
    router = Router(name='clarify-chat')

    @router.message(F.text)
    async def chat_intents(message: Message):
        text = (message.text or '').strip()
        if not text or text.startswith('/'):
            raise SkipHandler

        user = await get_user(ctx, message.from_user)
        active = await ctx.conversations.recent_materials(user.id, 3)
        decision = classify_text_intent(text, bool(active))

        if decision.name == 'greeting':
            return await message.answer(GREETING_TEXT)
        if decision.name == 'about':
            return await message.answer(ABOUT_TEXT)
        if decision.name == 'capabilities':
            return await message.answer(CAPABILITIES_TEXT)
        if decision.name == 'help':
            return await message.answer(HELP_TEXT)
        if decision.name == 'examples':
            return await message.answer(EXAMPLES_TEXT)
        if decision.name == 'general_chat':
            low = text.lower()
            if any(word in low for word in ('спасибо', 'спс', 'благодарю')):
                return await message.answer('Пожалуйста 🙂 Если есть ещё материал — отправляй, разберём.')
            if low in {'понял', 'понятно'}:
                return await message.answer('Отлично. Если что-то останется непонятным — просто спроси.')
            return await message.answer('Всё отлично — готов разбираться в информации 😄 Что посмотрим?')

        if not active and looks_like_followup(text):
            return await message.answer(NO_CONTEXT_TEXT)

        # /clear must also protect against the legacy general router consulting an
        # older saved material. Short requests such as «какие риски?» are treated
        # as missing-context after a clear, while a genuinely new long text still
        # passes through for normal analysis.
        if not active and len(text) <= 240:
            raw_latest = await ctx.materials.latest(user.id, 1)
            if raw_latest:
                stale_decision = classify_text_intent(text, True)
                if stale_decision.uses_recent_material or looks_like_followup(text):
                    return await message.answer(NO_CONTEXT_TEXT)

        raise SkipHandler

    return router
