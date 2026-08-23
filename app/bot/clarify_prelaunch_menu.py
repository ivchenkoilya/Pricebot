from __future__ import annotations

from aiogram import F, Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from app.bot.razberi_helpers import get_user
from app.bot.razberi_keyboards import (
    BTN_BACK,
    BTN_MEMORY,
    BTN_MORE,
    BTN_PROFILE,
    LEGACY_MEMORY,
    LEGACY_MEMORY_RU,
    main_menu,
    materials_list,
    more_menu,
    quick_webapp_url,
)


def build_prelaunch_menu_router(ctx) -> Router:
    """High-priority handlers for the simplified pre-launch keyboard."""
    router = Router(name='clarify-prelaunch-menu')

    @router.message(F.text.in_({BTN_MEMORY, LEGACY_MEMORY, LEGACY_MEMORY_RU}))
    async def materials(message: Message):
        user = await get_user(ctx, message.from_user)
        items = await ctx.materials.latest(user.id, 10)
        if not items:
            return await message.answer(
                '🧠 <b>Материалов пока нет.</b>\n\n'
                'Отправь голосовое, документ, фото, переписку, ссылку или текст — Clarify сохранит разбор здесь.'
            )
        await message.answer(
            '🧠 <b>Материалы</b>\n\n'
            'Последние разборы. Открой любой или спроси обычным сообщением, например: '
            '«найди, где было про оплату».',
            reply_markup=materials_list(items),
        )

    @router.message(F.text == BTN_PROFILE)
    async def profile_fallback(message: Message):
        url = quick_webapp_url(ctx.settings.webapp_url, 'profile')
        if url.startswith('https://'):
            return await message.answer(
                '👤 <b>Профиль</b>',
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text='Открыть профиль', web_app=WebAppInfo(url=url)),
                ]]),
            )
        await message.answer('Открой /profile — там тариф, лимиты и бонусы.')

    @router.message(F.text == BTN_MORE)
    async def more_fallback(message: Message):
        await message.answer(
            '••• <b>Дополнительные функции</b>\n\n'
            'Здесь остались проекты, сравнение, поддержка, настройки и очистка. '
            'Основное меню остаётся коротким.',
            reply_markup=more_menu(ctx.settings.webapp_url),
        )

    @router.message(F.text == BTN_BACK)
    async def back_to_main(message: Message):
        await message.answer(
            'Готово — вернул основное меню.',
            reply_markup=main_menu(ctx.settings.webapp_url),
        )

    return router
