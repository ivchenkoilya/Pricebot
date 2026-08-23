from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from app.bot.razberi_helpers import esc, get_user
from app.bot.razberi_keyboards import main_menu, quick_webapp_url
from app.brand import clarify_banner_jpeg


START_TEXT = (
    '<b>Привет! Я Clarify.</b>\n\n'
    'Отправь голосовое, документ, фото, переписку или ссылку — я выделю '
    '<b>главное, задачи, сроки, суммы и риски</b>.\n\n'
    'А потом можешь задать любые вопросы по материалу.\n\n'
    '👇 Просто отправь что-нибудь или посмотри пример.'
)

CAPABILITIES_TEXT = (
    '<b>Что умеет Clarify</b>\n\n'
    '🎤 <b>Голосовые и аудио</b> — расшифровка, суть и действия.\n\n'
    '📄 <b>Документы</b> — PDF, DOCX, TXT, MD, XLSX и CSV; сроки, суммы и риски.\n\n'
    '🖼 <b>Фото и скриншоты</b> — текст, смысл и важные детали.\n\n'
    '💬 <b>Переписки</b> — что от тебя хотят и готовый ответ.\n\n'
    '🔗 <b>Ссылки</b> — чтение доступных страниц и разбор содержимого.\n\n'
    '🧠 <b>Материалы</b> — поиск и вопросы по тому, что ты уже отправлял.\n\n'
    '📁 <b>Проекты</b> — связанные материалы в одной рабочей теме.'
)

EXAMPLES_TEXT = (
    '<b>Что можно спросить</b>\n\n'
    '• «Что здесь главное?»\n'
    '• «Что от меня требуется?»\n'
    '• «Какие сроки и суммы?»\n'
    '• «Объясни простыми словами»\n'
    '• «Какие здесь риски?»\n'
    '• «Сделай короткий ответ отправителю»\n\n'
    '<b>Или просто отправь материал — Clarify сам предложит подходящие действия.</b>'
)

HELP_TEXT = (
    '<b>Как пользоваться Clarify</b>\n\n'
    '📎 <b>Разобрать</b> — отправь голосовое, документ, фото, переписку, ссылку или текст.\n\n'
    '✍️ <b>Написать</b> — подготовить ответ или сообщение в нужном тоне.\n\n'
    '🧠 <b>Материалы</b> — найти старый разбор или спросить по сохранённой информации.\n\n'
    '👤 <b>Профиль</b> — лимиты, тариф, бонусы и приглашения.\n\n'
    'Если что-то не работает, открой <b>Профиль → Помощь и поддержка</b>.\n\n'
    '<small>Команды: /start · /profile · /invite · /clear</small>'
)

ABOUT_TEXT = (
    '<b>Clarify — AI-помощник внутри Telegram.</b>\n\n'
    'Он помогает быстро понимать документы, голосовые, изображения, сообщения и ссылки, '
    'а затем превращает информацию в конкретные действия.'
)

HOW_TEXT = (
    '<b>Как это работает</b>\n\n'
    'Clarify определяет тип материала, извлекает содержимое, делает структурированный разбор и сохраняет его в «Материалы». '
    'После этого можно продолжать обычным языком: «а срок?», «что по цене?», «объясни проще?». '
    'Повторно загружать файл не нужно.'
)

NO_CONTEXT_TEXT = (
    'Я пока не вижу активного материала для этого вопроса.\n\n'
    'Отправь документ, голосовое, изображение, текст или ссылку — и продолжим по нему.'
)


def _start_payload(message: Message) -> str:
    text = (message.text or '').strip()
    if ' ' not in text:
        return ''
    return text.split(maxsplit=1)[1].strip()[:255]


def _start_keyboard(webapp_url: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    url = quick_webapp_url(webapp_url)
    if url.startswith('https://'):
        rows.append([InlineKeyboardButton(text='🚀 Открыть Clarify', web_app=WebAppInfo(url=url))])
    rows += [
        [
            InlineKeyboardButton(text='🎙 Голосовое', callback_data='growth:hint:voice'),
            InlineKeyboardButton(text='📄 Документ', callback_data='growth:hint:document'),
        ],
        [
            InlineKeyboardButton(text='📷 Фото / скриншот', callback_data='growth:hint:image'),
            InlineKeyboardButton(text='💬 Переписка', callback_data='growth:hint:chat'),
        ],
        [InlineKeyboardButton(text='✨ Посмотреть пример', callback_data='growth:demo')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_start_router(ctx) -> Router:
    router = Router(name='clarify-start')
    settings = ctx.settings

    async def send_start(message: Message) -> None:
        user = await get_user(ctx, message.from_user)
        await ctx.growth.capture_start(user.id, _start_payload(message))
        await ctx.metrics.inc('starts', user.id)
        menu_attached = False
        try:
            await message.answer_photo(
                BufferedInputFile(clarify_banner_jpeg(), filename='clarify-start.jpg'),
                reply_markup=main_menu(settings.webapp_url),
            )
            menu_attached = True
        except Exception as exc:
            await ctx.errors.record('start-banner', message.from_user.id, 'start_banner', exc)

        if not menu_attached:
            try:
                temp = await message.answer('\u2063', reply_markup=main_menu(settings.webapp_url))
                await temp.delete()
            except Exception:
                pass

        await message.answer(START_TEXT, reply_markup=_start_keyboard(settings.webapp_url))

    @router.message(CommandStart())
    async def start(message: Message):
        await send_start(message)

    @router.message(Command('help'))
    async def help_command(message: Message):
        await message.answer(HELP_TEXT, reply_markup=main_menu(settings.webapp_url))

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
