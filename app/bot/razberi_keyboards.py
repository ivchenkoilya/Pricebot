from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='📎 Разобрать'), KeyboardButton(text='✍️ Написать')],
            [KeyboardButton(text='🧠 Мои материалы'), KeyboardButton(text='🔀 Сравнить')],
            [KeyboardButton(text='📁 Проекты'), KeyboardButton(text='👑 PRO')],
            [KeyboardButton(text='⚙️ Настройки'), KeyboardButton(text='❓ Помощь')],
            [KeyboardButton(text='🛟 Поддержка / сообщить об ошибке')],
        ],
        resize_keyboard=True,
    )


def actions(material_id: int, material_type: str = '') -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text='⚡ Кратко', callback_data=f'mat:{material_id}:summary'),
            InlineKeyboardButton(text='📌 Главное', callback_data=f'mat:{material_id}:main'),
        ],
        [
            InlineKeyboardButton(text='🧠 Простыми словами', callback_data=f'mat:{material_id}:plain'),
            InlineKeyboardButton(text='✅ Что делать', callback_data=f'mat:{material_id}:tasks'),
        ],
    ]
    type_low = (material_type or '').lower()
    if type_low in {'pdf', 'docx', 'txt', 'md', 'xlsx', 'csv', 'document'}:
        rows += [
            [
                InlineKeyboardButton(text='⚠️ Риски', callback_data=f'mat:{material_id}:risks'),
                InlineKeyboardButton(text='💰 Деньги', callback_data=f'mat:{material_id}:money'),
            ],
            [
                InlineKeyboardButton(text='📅 Сроки', callback_data=f'mat:{material_id}:dates'),
                InlineKeyboardButton(text='❓ Задать вопрос', callback_data=f'mat:{material_id}:ask'),
            ],
        ]
    elif type_low in {'voice', 'audio', 'forwarded'}:
        rows += [
            [
                InlineKeyboardButton(text='🎯 Что от меня хотят?', callback_data=f'mat:{material_id}:wants'),
                InlineKeyboardButton(text='✍️ Ответить', callback_data=f'mat:{material_id}:reply'),
            ],
            [
                InlineKeyboardButton(text='⚠️ Риски', callback_data=f'mat:{material_id}:risks'),
                InlineKeyboardButton(text='❓ Задать вопрос', callback_data=f'mat:{material_id}:ask'),
            ],
        ]
    else:
        rows += [[
            InlineKeyboardButton(text='⚠️ Риски', callback_data=f'mat:{material_id}:risks'),
            InlineKeyboardButton(text='❓ Задать вопрос', callback_data=f'mat:{material_id}:ask'),
        ]]

    rows += [
        [
            InlineKeyboardButton(text='⏰ Напомнить', callback_data=f'mat:{material_id}:remind'),
            InlineKeyboardButton(text='📁 В проект', callback_data=f'mat:{material_id}:project'),
        ],
        [
            InlineKeyboardButton(text='📄 Исходник', callback_data=f'mat:{material_id}:source'),
            InlineKeyboardButton(text='🗑 Удалить', callback_data=f'mat:{material_id}:delete'),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def materials_list(items) -> InlineKeyboardMarkup:
    rows = []
    for material in items[:10]:
        title = (material.title or 'Материал').replace('\n', ' ')[:42]
        rows.append([InlineKeyboardButton(text=f'#{material.id} · {title}', callback_data=f'matopen:{material.id}')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def projects_list(items) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f'📁 {item.name[:45]}', callback_data=f'projopen:{item.id}')]
        for item in items[:20]
    ]
    rows.append([InlineKeyboardButton(text='➕ Новый проект', callback_data='proj:new')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def project_picker(material_id: int, projects) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f'📁 {project.name[:42]}', callback_data=f'projadd:{material_id}:{project.id}')]
        for project in projects[:15]
    ]
    rows.append([InlineKeyboardButton(text='➕ Создать проект', callback_data=f'projnew:{material_id}')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pro_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text='👑 Подключить PRO', callback_data='pro:buy')]]
    )


def reminder_confirm(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text='✅ Создать', callback_data=f'rem:{reminder_id}:yes'),
                InlineKeyboardButton(text='❌ Отмена', callback_data=f'rem:{reminder_id}:no'),
            ]
        ]
    )


def forwarded_actions(material_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text='🎯 Что хотят?', callback_data=f'mat:{material_id}:wants'),
                InlineKeyboardButton(text='🧠 Простыми словами', callback_data=f'mat:{material_id}:plain'),
            ],
            [
                InlineKeyboardButton(text='1️⃣ Нейтрально', callback_data=f'fwd:{material_id}:neutral'),
                InlineKeyboardButton(text='2️⃣ Дружелюбно', callback_data=f'fwd:{material_id}:friendly'),
            ],
            [
                InlineKeyboardButton(text='3️⃣ Коротко', callback_data=f'fwd:{material_id}:short'),
                InlineKeyboardButton(text='4️⃣ С юмором', callback_data=f'fwd:{material_id}:humor'),
            ],
            [
                InlineKeyboardButton(text='❓ Задать вопрос', callback_data=f'mat:{material_id}:ask'),
                InlineKeyboardButton(text='📁 В проект', callback_data=f'mat:{material_id}:project'),
            ],
        ]
    )


def draft_actions(material_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text='🙂 Мягче', callback_data=f'draft:{material_id}:soft'),
                InlineKeyboardButton(text='💼 Официальнее', callback_data=f'draft:{material_id}:formal'),
            ],
            [
                InlineKeyboardButton(text='⚡ Короче', callback_data=f'draft:{material_id}:short'),
                InlineKeyboardButton(text='😏 С юмором', callback_data=f'draft:{material_id}:humor'),
            ],
            [
                InlineKeyboardButton(text='🔥 Убедительнее', callback_data=f'draft:{material_id}:persuasive'),
                InlineKeyboardButton(text='♻️ Другой вариант', callback_data=f'draft:{material_id}:alternative'),
            ],
        ]
    )


def admin_test_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text='🤖 Проверить AI', callback_data='admtest:ai'),
                InlineKeyboardButton(text='🎤 Проверить STT', callback_data='admtest:stt'),
            ],
            [
                InlineKeyboardButton(text='💾 Проверить DB', callback_data='admtest:db'),
                InlineKeyboardButton(text='⏰ Проверить Scheduler', callback_data='admtest:scheduler'),
            ],
            [
                InlineKeyboardButton(text='📊 Usage', callback_data='admtest:usage'),
                InlineKeyboardButton(text='⚠️ Последние ошибки', callback_data='admtest:errors'),
            ],
        ]
    )


def delete_data_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text='🗑 Да, удалить', callback_data='privacy:confirm'),
            InlineKeyboardButton(text='❌ Отмена', callback_data='privacy:cancel'),
        ]]
    )
