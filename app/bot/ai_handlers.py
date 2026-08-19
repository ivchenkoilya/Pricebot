from __future__ import annotations

import html
import re

from aiogram import F, Router
from aiogram.filters import BaseFilter, Command, StateFilter
from aiogram.types import Message

from app.services.ai import AIService

MENU_TEXTS = {
    '➕ Добавить',
    '🔔 Мои товары',
    '🔥 Снижения',
    '🔎 Найти дешевле',
    '👑 PRO',
    '⚙️ Настройки',
}
URLISH_RE = re.compile(r'(?:https?://|www\.|\b[a-z0-9-]+\.(?:ru|com|net|org|io|shop|рф)\b)', re.I)
NUMBER_ONLY_RE = re.compile(r'[\d\s\u00a0\u2009\u202f.,₽%]+')


def is_ai_candidate_text(text: str | None) -> bool:
    if not text:
        return False
    value = text.strip()
    if len(value) < 3 or len(value) > 500:
        return False
    if value.startswith('/') or value in MENU_TEXTS:
        return False
    if URLISH_RE.search(value) or NUMBER_ONLY_RE.fullmatch(value):
        return False
    return bool(re.search(r'[A-Za-zА-Яа-яЁё]', value))


class ProductTextCandidateFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return is_ai_candidate_text(message.text)


def _safe(value: str | None) -> str:
    return html.escape((value or '').strip())


def create_ai_router(ai: AIService) -> Router:
    router = Router(name='price-ai')

    @router.message(Command('ai_status'))
    async def ai_status(message: Message):
        if ai.enabled:
            await message.answer(f'🤖 AI: <b>ON</b>\nМодель: <code>{html.escape(ai.settings.openai_model)}</code>')
        else:
            await message.answer('🤖 AI: <b>OFF</b>\nДобавь OPENAI_API_KEY в secrets Amvera и перезапусти приложение.')

    if not ai.enabled:
        return router

    @router.message(StateFilter(None), F.text, ProductTextCandidateFilter())
    async def understand_product(message: Message):
        intent = await ai.analyze_product_text(message.text or '')
        if intent is None:
            return await message.answer(
                '🤖 AI сейчас не смог разобрать сообщение. Пришли ссылку на товар — обычное отслеживание PRICE продолжает работать.'
            )

        if not intent.is_product or intent.confidence < 0.45:
            return await message.answer(
                'Я могу понять название товара обычным текстом. Например: <code>iPhone 16 Pro 256 чёрный</code> или <code>найди дешевле Sony WH-1000XM6</code>.'
            )

        title = _safe(intent.normalized_name or intent.search_query or intent.model or intent.brand or 'Товар')
        lines = ['🤖 <b>Понял товар</b>', '', f'<b>{title}</b>']
        if intent.brand:
            lines.append(f'Бренд: {_safe(intent.brand)}')
        if intent.model:
            lines.append(f'Модель: {_safe(intent.model)}')
        if intent.variant:
            lines.append(f'Версия: {_safe(intent.variant)}')

        if intent.action == 'find_cheaper':
            lines += ['', '🔎 Понял, что нужно найти дешевле. Для реального сравнения пришли ссылку на исходный товар.']
        elif intent.action == 'track':
            lines += ['', '🔔 Понял, что нужно следить за ценой. Пришли ссылку на карточку товара.']
        elif intent.action == 'set_target':
            condition = []
            if intent.target_price is not None:
                condition.append(f'цена ≤ {intent.target_price:,.0f}'.replace(',', ' '))
            if intent.target_percent is not None:
                condition.append(f'снижение ≥ {intent.target_percent:g}%')
            lines += ['', '🎯 Понял условие' + (f': {", ".join(condition)}' if condition else '.')]
            lines.append('Сначала пришли ссылку на сам товар, чтобы PRICE получил его реальную цену.')
        else:
            lines += ['', 'Теперь пришли ссылку на карточку этого товара.']

        lines += ['', 'Цена через AI не придумывается — её по-прежнему получает provider магазина.']
        await message.answer('\n'.join(lines))

    return router
