from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='➕ Добавить'), KeyboardButton(text='🔔 Мои товары')],
            [KeyboardButton(text='🔥 Снижения'), KeyboardButton(text='🔎 Найти дешевле')],
            [KeyboardButton(text='👑 PRO'), KeyboardButton(text='⚙️ Настройки')],
        ],
        resize_keyboard=True,
        input_field_placeholder='Пришли ссылку на товар',
    )


def product_keyboard(product_id: int, url: str, watching: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text='🎯 Условие', callback_data=f'target:{product_id}'), InlineKeyboardButton(text='📊 История', callback_data=f'history:{product_id}')],
        [InlineKeyboardButton(text='🏆 Новый минимум', callback_data=f'newlow:{product_id}'), InlineKeyboardButton(text='📦 Наличие', callback_data=f'stock:{product_id}')],
        [InlineKeyboardButton(text='⏸ Не следить' if watching else '🔔 Следить', callback_data=f'pause:{product_id}' if watching else f'follow:{product_id}')],
        [InlineKeyboardButton(text='🛒 Открыть', url=url)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_panel() -> InlineKeyboardMarkup:
    labels = [
        ('🔗 Проверить URL сейчас', 'admin:check_url'),
        ('⏱ Scheduler сейчас', 'admin:scheduler'),
        ('📉 Тестовое падение', 'admin:test_drop'),
        ('🔔 Симулировать уведомление', 'admin:test_alert'),
        ('📦 Товары', 'admin:products'),
        ('👀 Watches', 'admin:watches'),
        ('⚠️ Ошибки providers', 'admin:errors'),
        ('🗄 Проверить БД', 'admin:db'),
        ('🧹 Очистить мои тестовые данные', 'admin:clear_me'),
        ('👑 Вкл/выкл PRO', 'admin:toggle_pro'),
    ]
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d)] for t, d in labels])
