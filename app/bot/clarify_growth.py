from __future__ import annotations

from urllib.parse import quote

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.razberi_helpers import esc, get_user
from app.services.core import bonus_requests, clarify_plan, plan_daily_ai_limit
from app.services.growth import build_referral_link


DEMO_TEXT = (
    '🎙 <b>Демо · голосовое 12:43</b>\n\n'
    '<b>Главное</b>\n'
    '• Поставщик подтвердил наличие товара.\n'
    '• Финальную цену пришлёт сегодня.\n'
    '• Отгрузка возможна после подтверждения оплаты.\n\n'
    '<b>Что от тебя хотят</b>\n'
    'Подтвердить количество и ответить, подходит ли срок поставки.\n\n'
    '<b>Задачи</b>\n'
    '1. Проверить количество.\n'
    '2. Ответить поставщику.\n'
    '3. После получения цены согласовать оплату.\n\n'
    '<b>Срок</b>\n'
    'Ответить желательно сегодня.\n\n'
    'Так же Clarify разбирает твои реальные голосовые, документы, скриншоты и переписки.'
)


HINTS = {
    'voice': '🎙 <b>Голосовое</b>\n\nПросто отправь голосовое сюда. Clarify расшифрует его и покажет главное, задачи и то, что от тебя хотят.',
    'document': '📄 <b>Документ</b>\n\nПрикрепи PDF, DOCX, TXT, MD, XLSX или CSV. Clarify найдёт главное, деньги, сроки и риски.',
    'image': '📷 <b>Скриншот</b>\n\nОтправь фото или скриншот. После разбора можно задавать уточняющие вопросы по этому же изображению.',
    'chat': '💬 <b>Переписка</b>\n\nПерешли сообщение или вставь текст. Clarify объяснит смысл и при необходимости подготовит ответ.',
}


def _share_url(link: str, text: str) -> str:
    return f'https://t.me/share/url?url={quote(link, safe="")}&text={quote(text, safe="")}'


def _invite_keyboard(link: str) -> InlineKeyboardMarkup:
    text = 'Попробуй Clarify: он разбирает голосовые, документы и переписки вместо тебя.'
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📤 Отправить другу', url=_share_url(link, text))],
        [InlineKeyboardButton(text='👤 Мой профиль', callback_data='growth:profile')],
    ])


async def _referral_link(ctx, telegram_id: int) -> str:
    me = await ctx.bot.get_me()
    return build_referral_link(me.username or '', telegram_id)


async def _send_invite(ctx, message: Message, telegram_user) -> None:
    user = await get_user(ctx, telegram_user)
    stats = await ctx.growth.stats(user.id)
    link = await _referral_link(ctx, telegram_user.id)
    bonus = int(ctx.settings.referral_bonus_requests)
    await message.answer(
        '<b>🎁 Пригласи друга в Clarify</b>\n\n'
        f'После его <b>первого успешного AI-разбора</b> вы оба получите +{bonus} запросов.\n\n'
        f'Приглашено: <b>{stats.invited_total}</b>\n'
        f'Сделали первый разбор: <b>{stats.rewarded_total}</b>\n'
        f'Заработано: <b>+{stats.earned_requests}</b> запросов\n\n'
        f'<code>{esc(link)}</code>',
        reply_markup=_invite_keyboard(link),
    )


async def _send_profile(ctx, message: Message, telegram_user) -> None:
    user = await get_user(ctx, telegram_user)
    stats = await ctx.growth.stats(user.id)
    used = await ctx.usage.ai_count_today(user.id)
    limit = plan_daily_ai_limit(user, ctx.settings)
    bonus = bonus_requests(user)
    limit_text = '∞' if limit is None else str(limit)
    campaign = f' · {stats.campaign}' if stats.campaign else ''
    await message.answer(
        '<b>👤 Профиль Clarify</b>\n\n'
        f'Тариф: <b>{clarify_plan(user, ctx.settings)}</b>\n'
        f'AI сегодня: <b>{used} / {limit_text}</b>\n'
        f'Бонусные запросы: <b>{bonus}</b>\n\n'
        f'👥 Приглашено: <b>{stats.invited_total}</b>\n'
        f'✅ Активировано: <b>{stats.rewarded_total}</b>\n'
        f'🎁 Получено за приглашения: <b>+{stats.earned_requests}</b>\n\n'
        f'Источник первого запуска: <b>{esc(stats.source)}</b>{esc(campaign)}',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='🎁 Пригласить друга', callback_data='growth:invite')],
            [InlineKeyboardButton(text='💎 Тарифы', callback_data='plans:open')],
        ]),
    )


def build_growth_router(ctx) -> Router:
    router = Router(name='clarify-growth')

    @router.message(Command('invite'))
    async def invite_command(message: Message):
        await _send_invite(ctx, message, message.from_user)

    @router.message(Command('profile'))
    async def profile_command(message: Message):
        await _send_profile(ctx, message, message.from_user)

    @router.message(Command('growth'))
    async def growth_dashboard(message: Message):
        if not ctx.settings.admin_telegram_id or message.from_user.id != ctx.settings.admin_telegram_id:
            return
        data = await ctx.growth.dashboard()
        sources = data.get('sources') or []
        source_text = '\n'.join(f'• {esc(source)} — {count}' for source, count in sources[:10]) or '• пока нет данных'
        registrations = int(data['registrations'])
        first_analyses = int(data['first_analyses'])
        conversion = (first_analyses / registrations * 100.0) if registrations else 0.0
        opened = int(data['referral_opened'])
        converted = int(data['referral_converted'])
        referral_conversion = (converted / opened * 100.0) if opened else 0.0
        await message.answer(
            '<b>📈 Clarify · growth</b>\n\n'
            f'Регистрации: <b>{registrations}</b>\n'
            f'Первый AI-разбор: <b>{first_analyses}</b> ({conversion:.1f}%)\n'
            f'Реферальные открытия: <b>{opened}</b>\n'
            f'Реферальные активации: <b>{converted}</b> ({referral_conversion:.1f}%)\n\n'
            '<b>Источники</b>\n' + source_text
        )

    @router.callback_query(F.data == 'growth:invite')
    async def invite_callback(callback: CallbackQuery):
        await _send_invite(ctx, callback.message, callback.from_user)
        await callback.answer()

    @router.callback_query(F.data == 'growth:profile')
    async def profile_callback(callback: CallbackQuery):
        await _send_profile(ctx, callback.message, callback.from_user)
        await callback.answer()

    @router.callback_query(F.data == 'growth:demo')
    async def demo_callback(callback: CallbackQuery):
        await ctx.metrics.inc('demo_opened')
        await callback.message.answer(
            DEMO_TEXT,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='📎 Попробовать со своим материалом', callback_data='growth:hint:voice')],
                [InlineKeyboardButton(text='🎁 Пригласить друга', callback_data='growth:invite')],
            ]),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith('growth:hint:'))
    async def hint_callback(callback: CallbackQuery):
        kind = callback.data.rsplit(':', 1)[-1]
        await callback.message.answer(HINTS.get(kind, 'Отправь материал в этот чат — Clarify сам определит его тип.'))
        await callback.answer()

    @router.callback_query(F.data.startswith('share:'))
    async def share_material(callback: CallbackQuery):
        user = await get_user(ctx, callback.from_user)
        try:
            material_id = int(callback.data.split(':', 1)[1])
        except (TypeError, ValueError):
            return await callback.answer('Материал не найден', show_alert=True)
        material = await ctx.materials.get(user.id, material_id)
        if material is None:
            return await callback.answer('Материал не найден', show_alert=True)

        link = await _referral_link(ctx, callback.from_user.id)
        type_labels = {
            'voice': 'голосовое', 'audio': 'аудио', 'pdf': 'PDF', 'docx': 'документ',
            'document': 'документ', 'image': 'скриншот', 'photo': 'скриншот',
            'forwarded': 'переписку', 'video': 'видео', 'text': 'текст',
        }
        label = type_labels.get((material.type or '').lower(), 'материал')
        text = (
            f'Я разобрал {label} в Clarify: вместо долгого просмотра получил главное, задачи и важные детали. '
            'Попробуй на своём материале.'
        )
        await callback.message.answer(
            '📤 <b>Поделиться Clarify</b>\n\n'
            'Приватное содержимое материала не отправляется — только ссылка на Clarify.',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='📤 Поделиться', url=_share_url(link, text))],
            ]),
        )
        await ctx.metrics.inc('share_opened', user.id)
        await callback.answer()

    return router
