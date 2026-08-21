from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from app.bot.razberi_helpers import esc, get_user
from app.brand import clarify_banner_jpeg


START_TEXT = (
    '<b>Привет! Я Clarify 👋</b>\n\n'
    'Разбираю голосовые, документы, скриншоты, сообщения и ссылки — и превращаю их в понятный результат.\n\n'
    '✨ Кратко · 📌 Главное · ✅ Действия · 📅 Сроки · ⚠️ Риски\n\n'
    '<b>Отправь материал в чат или открой Clarify.</b>'
)

CAPABILITIES_TEXT = (
    '<b>Возможности Clarify</b>\n\n'
    '🎤 <b>Голосовые и аудио</b> — быстрая расшифровка, суть и действия.\n\n'
    '📄 <b>Документы</b> — PDF, DOCX, TXT, MD, XLSX и CSV.\n\n'
    '🖼 <b>Фото и скриншоты</b> — текст, смысл, ошибки и важные детали.\n\n'
    '🔗 <b>Ссылки</b> — чтение доступных страниц и разбор содержимого.\n\n'
    '🎬 <b>Видео-ссылки</b> — расшифровка и AI-разбор; скачивание видео появится позже.\n\n'
    '🧠 <b>Memory</b> — вопросы по сохранённым материалам.\n\n'
    '📁 <b>Проекты</b> — связанные материалы в одной рабочей теме.\n\n'
    '✍️ <b>Написать за меня</b> — готовые сообщения в нужном стиле.'
)

EXAMPLES_TEXT = (
    '<b>Примеры</b>\n\n'
    '• «Что здесь главное?»\n'
    '• «Что от меня требуется?»\n'
    '• «Какие сроки и суммы?»\n'
    '• «Объясни простыми словами»\n'
    '• «Какие здесь риски?»\n'
    '• «Сделай короткий ответ отправителю»\n'
    '• «Кратко расскажи, о чём ролик» + ссылка\n\n'
    '<b>Или просто отправь материал без пояснений.</b>'
)

HELP_TEXT = (
    '<b>Как пользоваться Clarify</b>\n\n'
    '1. Отправь материал в чат или через Mini App.\n'
    '2. Clarify сохранит его в Memory и покажет результат.\n'
    '3. Выбери быстрое действие или задай свой вопрос.\n'
    '4. Для новой темы используй /clear.\n\n'
    '<b>Команды:</b>\n/start — старт\n/help — помощь\n/about — о Clarify\n/examples — примеры\n'
    '/summary — последний материал\n/clear — очистить контекст'
)

ABOUT_TEXT = (
    '<b>Clarify — AI Workspace внутри Telegram.</b>\n\n'
    'Он помогает быстро понимать документы, голосовые, изображения, сообщения и ссылки. '
    'Меньше времени на разбор информации — больше ясности и конкретных действий.'
)

HOW_TEXT = (
    '<b>Как это работает</b>\n\n'
    'Clarify определяет тип материала, извлекает содержимое, делает структурированный разбор и сохраняет его в Memory. '
    'После этого можно продолжать обычным языком: «а срок?», «что по цене?», «объясни проще?». '
    'В Mini App те же материалы доступны как личная база знаний.'
)

NO_CONTEXT_TEXT = (
    'Я пока не вижу активного материала для этого вопроса.\n\n'
    'Отправь документ, голосовое, изображение, текст или ссылку — и продолжим по нему.'
)


def _start_keyboard(webapp_url: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if webapp_url.strip().startswith('https://'):
        rows.append([InlineKeyboardButton(text='🚀 Открыть Clarify', web_app=WebAppInfo(url=webapp_url.strip()))])
    rows += [
        [
            InlineKeyboardButton(text='✨ Возможности', callback_data='start:capabilities'),
            InlineKeyboardButton(text='💡 Примеры', callback_data='start:examples'),
        ],
        [InlineKeyboardButton(text='❓ Помощь', callback_data='start:help')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_start_router(ctx) -> Router:
    router = Router(name='clarify-start')
    settings = ctx.settings

    async def send_start(message: Message) -> None:
        user = await get_user(ctx, message.from_user)
        await ctx.metrics.inc('starts', user.id)
        try:
            await message.answer_photo(BufferedInputFile(clarify_banner_jpeg(), filename='clarify-start.jpg'))
        except Exception as exc:
            await ctx.errors.record('start-banner', message.from_user.id, 'start_banner', exc)
        await message.answer(START_TEXT, reply_markup=_start_keyboard(settings.webapp_url))

    @router.message(CommandStart())
    async def start(message: Message):
        await send_start(message)

    @router.message(Command('help'))
    async def help_command(message: Message):
        await message.answer(HELP_TEXT)

    @router.message(Command('about'))
    async def about_command(message: Message):
        await message.answer(ABOUT_TEXT)

    @router.message(Command('examples'))
    async def examples_command(message: Message):
        await message.answer(EXAMPLES_TEXT)

    @router.message(Command('summary'))
    async def summary_command(message: Message):
        user = await get_user(ctx, message.from_user)
        items = await ctx.conversations.recent_materials(user.id, 1)
        if not items:
            return await message.answer('Пока нечего сокращать. Отправь материал — и я сделаю выжимку.')
        material = items[0]
        await message.answer(
            f'✨ <b>{esc(material.title or "Последний материал")}</b>\n\n'
            f'{esc(material.summary or "Краткая выжимка пока не сохранена.")}'
        )

    @router.message(Command('clear'))
    async def clear_command(message: Message):
        user = await get_user(ctx, message.from_user)
        await ctx.conversations.clear(user.id)
        await message.answer('<b>Контекст очищен 🧹</b>\n\nТеперь можешь отправить новый материал.')

    @router.callback_query(F.data == 'start:capabilities')
    async def capabilities(callback: CallbackQuery):
        await callback.message.answer(CAPABILITIES_TEXT)
        await callback.answer()

    @router.callback_query(F.data == 'start:examples')
    async def examples(callback: CallbackQuery):
        await callback.message.answer(EXAMPLES_TEXT)
        await callback.answer()

    @router.callback_query(F.data == 'start:help')
    async def help_(callback: CallbackQuery):
        await callback.message.answer(HELP_TEXT)
        await callback.answer()

    @router.callback_query(F.data == 'start:how')
    async def how(callback: CallbackQuery):
        await callback.message.answer(HOW_TEXT)
        await callback.answer()

    @router.callback_query(F.data == 'start:clear')
    async def clear_callback(callback: CallbackQuery):
        user = await get_user(ctx, callback.from_user)
        await ctx.conversations.clear(user.id)
        await callback.message.answer('<b>Контекст очищен 🧹</b>\n\nТеперь можешь отправить новый материал.')
        await callback.answer('Контекст очищен')

    return router
