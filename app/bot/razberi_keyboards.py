from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)


BTN_UNPACK = '📎 Разобрать'
BTN_WRITE = '✍️ Написать'
BTN_MEMORY = '🧠 Memory'
BTN_COMPARE = '🔀 Сравнить'
BTN_PROJECTS = '📁 Проекты'
BTN_INBOX = '✨ AI Inbox'
BTN_PLANS = '💎 Тарифы'
BTN_SUPPORT = '🛟 Поддержка'
BTN_SETTINGS = '⚙️ Настройки'
BTN_CLEAR = '🗑 Очистить'
BTN_HELP = '❓ Помощь'
BTN_MINIAPP = '🏠 Mini App'

# Kept temporarily so users with an old persistent Telegram keyboard do not
# lose functionality before /start refreshes it.
LEGACY_MEMORY = '🧠 Мои материалы'
LEGACY_SUPPORT = '🛟 Поддержка / сообщить об ошибке'
LEGACY_CLEAR = '🗑 Очистить материалы'


def main_menu(webapp_url: str = '') -> ReplyKeyboardMarkup:
    mini_app = KeyboardButton(text=BTN_MINIAPP)
    # Important: use exactly the same final URL that /start uses. Do not append
    # /app/ or rewrite the path here; a different URL caused the reply-keyboard
    # WebApp to open a blank Telegram view while the /start inline button worked.
    url = (webapp_url or '').strip()
    if url.startswith('https://'):
        mini_app = KeyboardButton(text=BTN_MINIAPP, web_app=WebAppInfo(url=url))

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_UNPACK), KeyboardButton(text=BTN_WRITE)],
            [KeyboardButton(text=BTN_MEMORY), KeyboardButton(text=BTN_INBOX)],
            [KeyboardButton(text=BTN_PROJECTS), KeyboardButton(text=BTN_COMPARE)],
            [KeyboardButton(text=BTN_PLANS), KeyboardButton(text=BTN_SUPPORT)],
            [KeyboardButton(text=BTN_SETTINGS), KeyboardButton(text=BTN_CLEAR)],
            [KeyboardButton(text=BTN_HELP), mini_app],
        ],
        resize_keyboard=True,
        input_field_placeholder='Сообщение или материал…',
    )


def plans_keyboard(settings) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f'👑 PRO · {settings.pro_stars_price} ⭐', callback_data='plan:buy:pro')],
        [InlineKeyboardButton(text=f'💎 PRO MAX · {settings.max_stars_price} ⭐', callback_data='plan:buy:max')],
        [
            InlineKeyboardButton(text=f'+100 · {settings.request_pack_100_stars} ⭐', callback_data='plan:buy:pack100'),
            InlineKeyboardButton(text=f'+500 · {settings.request_pack_500_stars} ⭐', callback_data='plan:buy:pack500'),
        ],
        [InlineKeyboardButton(text=f'+2000 запросов · {settings.request_pack_2000_stars} ⭐', callback_data='plan:buy:pack2000')],
    ])


def actions(material_id: int, material_type: str = '') -> InlineKeyboardMarkup:
    type_low = (material_type or '').lower()
    rows: list[list[InlineKeyboardButton]] = []
    if type_low == 'video':
        rows.append([InlineKeyboardButton(text='⭕ Сделать кружок', callback_data=f'circle:{material_id}')])

    rows += [
        [
            InlineKeyboardButton(text='⚡ Кратко', callback_data=f'mat:{material_id}:summary'),
            InlineKeyboardButton(text='📌 Главное', callback_data=f'mat:{material_id}:main'),
        ],
        [
            InlineKeyboardButton(text='🧠 Простыми словами', callback_data=f'mat:{material_id}:plain'),
            InlineKeyboardButton(text='✅ Что делать', callback_data=f'mat:{material_id}:tasks'),
        ],
    ]
    if type_low in {'pdf', 'docx', 'txt', 'md', 'xlsx', 'csv', 'document'}:
        rows += [
            [InlineKeyboardButton(text='⚠️ Риски', callback_data=f'mat:{material_id}:risks'), InlineKeyboardButton(text='💰 Деньги', callback_data=f'mat:{material_id}:money')],
            [InlineKeyboardButton(text='📅 Сроки', callback_data=f'mat:{material_id}:dates'), InlineKeyboardButton(text='❓ Задать вопрос', callback_data=f'mat:{material_id}:ask')],
        ]
    elif type_low in {'voice', 'audio', 'forwarded', 'video', 'video_note'}:
        rows += [
            [InlineKeyboardButton(text='🎯 Что от меня хотят?', callback_data=f'mat:{material_id}:wants'), InlineKeyboardButton(text='✍️ Ответить', callback_data=f'mat:{material_id}:reply')],
            [InlineKeyboardButton(text='⚠️ Риски', callback_data=f'mat:{material_id}:risks'), InlineKeyboardButton(text='❓ Задать вопрос', callback_data=f'mat:{material_id}:ask')],
        ]
    else:
        rows += [[InlineKeyboardButton(text='⚠️ Риски', callback_data=f'mat:{material_id}:risks'), InlineKeyboardButton(text='❓ Задать вопрос', callback_data=f'mat:{material_id}:ask')]]

    rows += [
        [InlineKeyboardButton(text='⏰ Напомнить', callback_data=f'mat:{material_id}:remind'), InlineKeyboardButton(text='📁 В проект', callback_data=f'mat:{material_id}:project')],
        [InlineKeyboardButton(text='📄 Исходник', callback_data=f'mat:{material_id}:source'), InlineKeyboardButton(text='🗑 Удалить', callback_data=f'mat:{material_id}:delete')],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def materials_list(items) -> InlineKeyboardMarkup:
    rows = []
    for material in items[:10]:
        title = (material.title or 'Материал').replace('\n', ' ')[:42]
        rows.append([InlineKeyboardButton(text=f'#{material.id} · {title}', callback_data=f'matopen:{material.id}')])
    rows.append([InlineKeyboardButton(text='🗑 Удалить все материалы', callback_data='materials:clear:ask')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def projects_list(items) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f'📁 {item.name[:45]}', callback_data=f'projopen:{item.id}')]
            for item in items[:20]]
    rows.append([InlineKeyboardButton(text='➕ Новый проект', callback_data='proj:new')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def project_picker(material_id: int, projects) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f'📁 {project.name[:42]}', callback_data=f'projadd:{material_id}:{project.id}')]
            for project in projects[:15]]
    rows.append([InlineKeyboardButton(text='➕ Создать проект', callback_data=f'projnew:{material_id}')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pro_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='💳 Открыть тарифы', callback_data='plans:open')]])


def reminder_confirm(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ Создать', callback_data=f'rem:{reminder_id}:yes'), InlineKeyboardButton(text='❌ Отмена', callback_data=f'rem:{reminder_id}:no')]])


def forwarded_actions(material_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🎯 Что хотят?', callback_data=f'mat:{material_id}:wants'), InlineKeyboardButton(text='🧠 Простыми словами', callback_data=f'mat:{material_id}:plain')],
        [InlineKeyboardButton(text='1️⃣ Нейтрально', callback_data=f'fwd:{material_id}:neutral'), InlineKeyboardButton(text='2️⃣ Дружелюбно', callback_data=f'fwd:{material_id}:friendly')],
        [InlineKeyboardButton(text='3️⃣ Коротко', callback_data=f'fwd:{material_id}:short'), InlineKeyboardButton(text='4️⃣ С юмором', callback_data=f'fwd:{material_id}:humor')],
        [InlineKeyboardButton(text='❓ Задать вопрос', callback_data=f'mat:{material_id}:ask'), InlineKeyboardButton(text='📁 В проект', callback_data=f'mat:{material_id}:project')],
    ])


def draft_actions(material_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🙂 Мягче', callback_data=f'draft:{material_id}:soft'), InlineKeyboardButton(text='💼 Официальнее', callback_data=f'draft:{material_id}:formal')],
        [InlineKeyboardButton(text='⚡ Короче', callback_data=f'draft:{material_id}:short'), InlineKeyboardButton(text='😏 С юмором', callback_data=f'draft:{material_id}:humor')],
        [InlineKeyboardButton(text='🔥 Убедительнее', callback_data=f'draft:{material_id}:persuasive'), InlineKeyboardButton(text='♻️ Другой вариант', callback_data=f'draft:{material_id}:alternative')],
    ])


def admin_test_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🤖 Проверить AI', callback_data='admtest:ai'), InlineKeyboardButton(text='🎤 Проверить STT', callback_data='admtest:stt')],
        [InlineKeyboardButton(text='💾 Проверить DB', callback_data='admtest:db'), InlineKeyboardButton(text='⏰ Проверить Scheduler', callback_data='admtest:scheduler')],
        [InlineKeyboardButton(text='📊 Usage', callback_data='admtest:usage'), InlineKeyboardButton(text='⚠️ Последние ошибки', callback_data='admtest:errors')],
    ])


def delete_data_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🗑 Да, удалить', callback_data='privacy:confirm'), InlineKeyboardButton(text='❌ Отмена', callback_data='privacy:cancel')]])