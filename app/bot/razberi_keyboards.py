from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)


BTN_UNPACK = '📎 Разобрать'
BTN_WRITE = '✍️ Написать'
BTN_MEMORY = '🧠 Материалы'
BTN_COMPARE = '🔀 Сравнить'
BTN_PROJECTS = '📁 Проекты'
BTN_INBOX = '✨ Важное'
BTN_PLANS = '💎 Тарифы'
BTN_SUPPORT = '🛟 Поддержка'
BTN_SETTINGS = '⚙️ Настройки'
BTN_CLEAR = '🗑 Очистить'
BTN_HELP = '❓ Помощь'
BTN_MINIAPP = '🏠 Clarify'
BTN_PROFILE = '👤 Профиль'
BTN_MORE = '••• Ещё'
BTN_BACK = '↩️ Основное меню'

# Old persistent Telegram keyboards can survive a deploy. Keep their labels
# routable even though the new menu no longer shows them.
LEGACY_MEMORY = '🧠 Memory'
LEGACY_MEMORY_RU = '🧠 Мои материалы'
LEGACY_SUPPORT = '🛟 Поддержка / сообщить об ошибке'
LEGACY_CLEAR = '🗑 Очистить материалы'


def quick_webapp_url(webapp_url: str = '', page: str | None = None) -> str:
    """Build a cache-busted Mini App URL and optionally deep-link to a page."""
    url = (webapp_url or '').strip()
    url = url.replace('http://pricebot2.ivch.amvera.io', 'https://pricebot2-ivch.amvera.io')
    url = url.replace('https://pricebot2.ivch.amvera.io', 'https://pricebot2-ivch.amvera.io')
    if not url.startswith('https://'):
        return url

    parts = urlsplit(url)
    path = parts.path or '/'
    if parts.netloc.lower() == 'pricebot2-ivch.amvera.io' and path in {'', '/'}:
        path = '/app/'

    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query['launch'] = 'keyboard'
    query['v'] = '20260823-2'
    if page:
        query['page'] = page
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), parts.fragment))


def _webapp_button(text: str, webapp_url: str, page: str) -> KeyboardButton:
    url = quick_webapp_url(webapp_url, page)
    if url.startswith('https://'):
        return KeyboardButton(text=text, web_app=WebAppInfo(url=url))
    return KeyboardButton(text=text)


def main_menu(webapp_url: str = '') -> ReplyKeyboardMarkup:
    """Compact six-action menu. Rare tools live one tap behind More."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_UNPACK), KeyboardButton(text=BTN_WRITE)],
            [KeyboardButton(text=BTN_MEMORY), _webapp_button(BTN_PROFILE, webapp_url, 'profile')],
            [KeyboardButton(text=BTN_PLANS), KeyboardButton(text=BTN_MORE)],
        ],
        resize_keyboard=True,
        input_field_placeholder='Сообщение или материал…',
    )


def more_menu(webapp_url: str = '') -> ReplyKeyboardMarkup:
    """Secondary menu keeps every advanced feature reachable without cluttering onboarding."""
    mini_app = _webapp_button(BTN_MINIAPP, webapp_url, 'home')
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_INBOX), KeyboardButton(text=BTN_PROJECTS)],
            [KeyboardButton(text=BTN_COMPARE), KeyboardButton(text=BTN_SUPPORT)],
            [KeyboardButton(text=BTN_SETTINGS), KeyboardButton(text=BTN_CLEAR)],
            [KeyboardButton(text=BTN_HELP), mini_app],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
        input_field_placeholder='Дополнительные функции…',
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
    """Show only actions that make sense for this material; rare actions stay below."""
    low = (material_type or '').lower()
    rows: list[list[InlineKeyboardButton]] = []
    if low == 'video':
        rows.append([InlineKeyboardButton(text='⭕ Сделать кружок', callback_data=f'circle:{material_id}')])

    rows.append([InlineKeyboardButton(text='❓ Задать вопрос', callback_data=f'mat:{material_id}:ask')])
    if low in {'image', 'photo', 'screenshot'}:
        rows.append([
            InlineKeyboardButton(text='📌 Детали', callback_data=f'mat:{material_id}:main'),
            InlineKeyboardButton(text='🧠 Объяснить', callback_data=f'mat:{material_id}:plain'),
        ])
    elif low in {'pdf', 'docx', 'txt', 'md', 'xlsx', 'csv', 'document', 'spreadsheet'}:
        rows += [
            [InlineKeyboardButton(text='📌 Главное', callback_data=f'mat:{material_id}:main'), InlineKeyboardButton(text='✅ Что делать', callback_data=f'mat:{material_id}:tasks')],
            [InlineKeyboardButton(text='📅 Сроки', callback_data=f'mat:{material_id}:dates'), InlineKeyboardButton(text='💰 Суммы', callback_data=f'mat:{material_id}:money')],
            [InlineKeyboardButton(text='⚠️ Риски', callback_data=f'mat:{material_id}:risks')],
        ]
    elif low in {'voice', 'audio', 'video', 'video_note'}:
        rows += [
            [InlineKeyboardButton(text='📌 Главное', callback_data=f'mat:{material_id}:main'), InlineKeyboardButton(text='✅ Задачи', callback_data=f'mat:{material_id}:tasks')],
            [InlineKeyboardButton(text='🎯 Что от меня хотят', callback_data=f'mat:{material_id}:wants'), InlineKeyboardButton(text='📅 Сроки', callback_data=f'mat:{material_id}:dates')],
        ]
    elif low in {'forwarded', 'text'}:
        rows += [
            [InlineKeyboardButton(text='📌 Главное', callback_data=f'mat:{material_id}:main'), InlineKeyboardButton(text='🎯 Что от меня хотят', callback_data=f'mat:{material_id}:wants')],
            [InlineKeyboardButton(text='✍️ Ответить', callback_data=f'mat:{material_id}:reply')],
        ]
    else:
        rows.append([
            InlineKeyboardButton(text='📌 Главное', callback_data=f'mat:{material_id}:main'),
            InlineKeyboardButton(text='✅ Что делать', callback_data=f'mat:{material_id}:tasks'),
        ])

    rows += [
        [InlineKeyboardButton(text='📤 Поделиться', callback_data=f'share:{material_id}')],
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
