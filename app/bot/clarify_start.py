from __future__ import annotations

import base64
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from app.bot.razberi_helpers import get_user
from app.bot.razberi_keyboards import main_menu, materials_list, pro_button
from app.services.core import is_creator


def _start_keyboard(webapp_url: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if webapp_url.strip().startswith('https://'):
        rows.append([InlineKeyboardButton(text='🚀 Открыть Clarify', web_app=WebAppInfo(url=webapp_url.strip()))])
    rows += [
        [
            InlineKeyboardButton(text='📎 Разобрать', callback_data='start:unpack'),
            InlineKeyboardButton(text='🧠 Мои материалы', callback_data='start:materials'),
        ],
        [
            InlineKeyboardButton(text='👑 PRO', callback_data='start:pro'),
            InlineKeyboardButton(text='❓ Как пользоваться', callback_data='start:help'),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _telegram_photo_bytes(path: Path) -> bytes:
    """Read the text-safe bundled JPEG payload used by Telegram and the Mini App."""
    encoded = path.read_text(encoding='ascii').strip()
    payload = base64.b64decode(encoded, validate=True)
    if not (payload.startswith(b'\xff\xd8') and payload.endswith(b'\xff\xd9')):
        raise ValueError('Clarify banner payload is not a JPEG')
    return payload


def build_start_router(ctx) -> Router:
    router = Router(name='clarify-start')
    settings = ctx.settings
    banner = Path(__file__).resolve().parents[2] / 'assets' / 'clarify_banner.jpg.b64'

    @router.message(CommandStart())
    async def start(message: Message):
        user = await get_user(ctx, message.from_user)
        try:
            await ctx.metrics.inc('starts', user.id)
        except Exception:
            # Metrics must never make the main entry point unusable.
            pass

        owner_line = '\n\n👑 <b>OWNER · Unlimited</b>' if is_creator(user, settings) else ''
        caption = (
            '✨ <b>Clarify</b>\n\n'
            '<b>Перешли то, на что не хочется тратить время.</b>\n\n'
            '🎤 голосовые  ·  📄 документы\n'
            '📸 фото и скриншоты  ·  🔗 ссылки\n'
            '💬 сообщения и переписки\n\n'
            'Я найду главное, задачи, сроки, суммы и риски — а потом можно просто спросить: '
            '«а оплатить когда?», «что от меня хотят?», «ответь ему».'
            f'{owner_line}'
        )
        keyboard = _start_keyboard(settings.webapp_url)

        sent_banner = False
        if banner.exists():
            try:
                photo = BufferedInputFile(_telegram_photo_bytes(banner), filename='clarify_banner.jpg')
                await message.answer_photo(photo, caption=caption, reply_markup=keyboard)
                sent_banner = True
            except Exception as exc:
                try:
                    await ctx.errors.record(f'start-{message.message_id}', user.telegram_id, 'start_banner', exc)
                except Exception:
                    pass

        # Never leave /start silent just because the branded image failed.
        if not sent_banner:
            await message.answer(caption, reply_markup=keyboard)

        await message.answer('Быстрые действия всегда под рукой 👇', reply_markup=main_menu())

    @router.callback_query(F.data == 'start:unpack')
    async def unpack(callback: CallbackQuery):
        await callback.message.answer('📎 Отправь текст, голосовое, документ, фото, скриншот или ссылку — Clarify сам поймёт, как это разобрать.')
        await callback.answer()

    @router.callback_query(F.data == 'start:materials')
    async def materials(callback: CallbackQuery):
        user = await get_user(ctx, callback.from_user)
        items = await ctx.materials.latest(user.id, 10)
        if not items:
            await callback.message.answer('🧠 Материалов пока нет. Отправь что-нибудь на разбор.')
        else:
            await callback.message.answer('🧠 <b>Последние материалы</b>', reply_markup=materials_list(items))
        await callback.answer()

    @router.callback_query(F.data == 'start:pro')
    async def pro(callback: CallbackQuery):
        user = await get_user(ctx, callback.from_user)
        if is_creator(user, settings):
            await callback.message.answer('👑 <b>OWNER · Unlimited</b>\n\nДля владельца Clarify лимиты отключены. Покупать PRO не нужно.')
        else:
            await callback.message.answer(
                f'👑 <b>Clarify PRO</b>\n\n🎤 Длинные голосовые\n📄 Большие документы\n🧠 Больше AI-запросов\n'
                f'📁 Проекты · 🔀 Сравнение · ⏰ Напоминания\n\n{settings.pro_stars_price} ⭐ / 30 дней',
                reply_markup=pro_button(),
            )
        await callback.answer()

    @router.callback_query(F.data == 'start:help')
    async def help_(callback: CallbackQuery):
        await callback.message.answer(
            '❓ <b>Как пользоваться Clarify</b>\n\n'
            '1. Просто отправь материал.\n'
            '2. Получи прямой ответ и главное.\n'
            '3. Продолжай спрашивать обычным языком.\n'
            '4. Сохраняй материалы в проекты, сравнивай и ставь напоминания.\n\n'
            'Mini App удобнее всего для истории, проектов, сравнения и работы с документами.'
        )
        await callback.answer()

    return router
