from __future__ import annotations

from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from app.bot.razberi_helpers import esc, get_user
from app.bot.razberi_keyboards import main_menu


START_TEXT = (
    '<b>Привет! Я Clarify 👋</b>\n\n'
    'Я AI-помощник, который помогает быстро разобраться в информации.\n\n'
    'Можешь отправить мне голосовое, сообщение, документ, скриншот или ссылку — '
    'я помогу понять суть, выделю главное и отвечу на вопросы.\n\n'
    '<b>Что я умею:</b>\n\n'
    '🎤 Голосовые — расшифрую и выделю главное\n'
    '📄 Документы — прочитаю и сделаю понятную выжимку\n'
    '🖼 Скриншоты — разберу содержимое изображения\n'
    '💬 Сообщения — сокращу и объясню смысл\n'
    '🔗 Ссылки — помогу разобраться в содержимом страницы\n'
    '📌 Главное — найду ключевые факты, сроки и действия\n'
    '❓ Вопросы — отвечу на уточнения по присланному материалу\n'
    '🧠 Объяснение — объясню сложное простыми словами\n\n'
    '<b>Просто отправь мне что-нибудь. Остальное я разберу сам.</b>'
)

CAPABILITIES_TEXT = (
    '<b>Возможности Clarify</b>\n\n'
    '🎤 <b>Голосовые</b>\nРасшифровываю речь и могу сделать короткую выжимку.\n\n'
    '📄 <b>Документы</b>\nРазбираю документы и выделяю важную информацию.\n\n'
    '🖼 <b>Скриншоты и изображения</b>\nПонимаю, что находится на изображении, и объясняю детали.\n\n'
    '💬 <b>Текст</b>\nСокращаю длинные сообщения, объясняю смысл и структурирую информацию.\n\n'
    '🔗 <b>Ссылки</b>\nИзвлекаю полезную информацию со страниц, если они доступны для чтения.\n\n'
    '📌 <b>Главное</b>\nНахожу ключевые факты, даты, суммы, требования и действия.\n\n'
    '🧠 <b>Простое объяснение</b>\nПеревожу сложный текст на понятный человеческий язык.\n\n'
    '❓ <b>Уточняющие вопросы</b>\nПосле анализа можно продолжить разговор и спрашивать о материале.\n\n'
    'Например: «А какой срок?», «Что от меня требуется?», «Объясни второй пункт», '
    '«Сделай короче», «Какие тут риски?».\n\n'
    '<b>Команды:</b>\n'
    '/start — стартовый экран\n'
    '/help — помощь\n'
    '/about — о Clarify\n'
    '/examples — примеры запросов\n'
    '/summary — кратко о последнем материале\n'
    '/clear — очистить контекст'
)

EXAMPLES_TEXT = (
    '<b>Попробуй спросить меня так:</b>\n\n'
    '• «Сократи это сообщение»\n'
    '• «Что здесь главное?»\n'
    '• «Объясни простыми словами»\n'
    '• «Что от меня требуется?»\n'
    '• «Какие здесь сроки?»\n'
    '• «Есть ли здесь риски?»\n'
    '• «Сделай список действий»\n'
    '• «Расскажи в двух предложениях»\n'
    '• «Что означает второй пункт?»\n'
    '• «Найди суммы и даты»\n\n'
    '<b>Или просто отправь материал без пояснений — Clarify сам определит, что с ним делать.</b>'
)

HELP_TEXT = (
    '<b>Как пользоваться Clarify</b>\n\n'
    '1. Отправь текст, голосовое, документ, фото, скриншот или ссылку.\n'
    '2. Clarify выделит смысл, важные факты, сроки, суммы и действия.\n'
    '3. Продолжай спрашивать обычным языком: «а какой срок?», «объясни проще», «что делать дальше?».\n'
    '4. Используй кнопки под разбором для короткой версии, главного, рисков и следующих действий.\n\n'
    '<b>Команды:</b>\n'
    '/start — стартовый экран\n/help — помощь\n/about — о Clarify\n/examples — примеры\n'
    '/summary — кратко о последнем материале\n/clear — очистить контекст'
)

ABOUT_TEXT = (
    '<b>Я Clarify — AI-помощник внутри Telegram.</b>\n\n'
    'Моя задача — превращать сложную и перегруженную информацию в понятный результат.\n\n'
    'Ты отправляешь голосовое, документ, сообщение, скриншот или ссылку, а я помогаю понять:\n'
    '• что произошло;\n• что здесь важно;\n• что нужно сделать;\n• какие есть сроки;\n• какие есть риски.\n\n'
    '<b>Проще говоря: отправляешь информацию → получаешь ясность.</b>'
)

HOW_TEXT = (
    '<b>Как это работает</b>\n\n'
    'Clarify сам определяет тип материала, извлекает полезное содержимое и делает понятный разбор. '
    'После этого материал остаётся активным контекстом, поэтому можно писать коротко: '
    '«а срок?», «кто это?», «сделай короче», «что от меня хотят?».\n\n'
    'Чтобы начать новую тему без связи с предыдущим материалом, используй /clear.'
)

NO_CONTEXT_TEXT = (
    'Пока не вижу активного материала, к которому относится вопрос. '
    'Отправь сообщение, документ, скриншот, голосовое или ссылку — и я разберусь.'
)


def _start_keyboard(webapp_url: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if webapp_url.strip().startswith('https://'):
        rows.append([InlineKeyboardButton(text='🚀 Открыть Clarify', web_app=WebAppInfo(url=webapp_url.strip()))])
    rows += [
        [
            InlineKeyboardButton(text='✨ Что умеет Clarify', callback_data='start:capabilities'),
            InlineKeyboardButton(text='💡 Примеры', callback_data='start:examples'),
        ],
        [
            InlineKeyboardButton(text='❓ Помощь', callback_data='start:help'),
            InlineKeyboardButton(text='🧠 Как это работает', callback_data='start:how'),
        ],
        [InlineKeyboardButton(text='🗑 Очистить контекст', callback_data='start:clear')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_start_router(ctx) -> Router:
    router = Router(name='clarify-start')
    settings = ctx.settings
    banner = Path(__file__).resolve().parents[2] / 'assets' / 'clarify_banner.webp'

    async def send_start(message: Message) -> None:
        user = await get_user(ctx, message.from_user)
        await ctx.metrics.inc('starts', user.id)
        if banner.exists():
            try:
                await message.answer_photo(FSInputFile(banner))
            except Exception as exc:
                await ctx.errors.record('start-banner', message.from_user.id, 'start_banner', exc)
        await message.answer(START_TEXT, reply_markup=_start_keyboard(settings.webapp_url))
        # Preserve the existing reply-keyboard tools (projects, compare, compose,
        # settings, PRO) without overloading the inline start card.
        await message.answer('Быстрые инструменты всегда под рукой 👇', reply_markup=main_menu())

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
            return await message.answer('Пока нечего сокращать. Отправь мне материал — и я сделаю выжимку.')
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
