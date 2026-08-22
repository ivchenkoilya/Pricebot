from datetime import datetime
from types import SimpleNamespace

from app.bot.razberi_keyboards import BTN_SUPPORT, main_menu
from app.webapp.auth import TelegramWebAppUser
from app.webapp.support import _support_text


def test_main_menu_contains_support_button():
    keyboard = main_menu()
    labels = [button.text for row in keyboard.keyboard for button in row]
    assert BTN_SUPPORT in labels


def test_support_message_contains_user_and_escapes_html():
    tg = TelegramWebAppUser(id=12345, first_name='Илья <test>', username='ilya')
    user = SimpleNamespace(telegram_id=12345, is_pro=False, pro_until=None)
    settings = SimpleNamespace(admin_telegram_id=999, version='1.0.0')
    text = _support_text(
        tg=tg,
        user=user,
        settings=settings,
        kind='bug',
        message='Кнопка <не работает> & зависает',
        page='Telegram Mini App',
    )
    assert '🐞 Ошибка' in text
    assert '<code>12345</code>' in text
    assert 'Илья &lt;test&gt;' in text
    assert 'Кнопка &lt;не работает&gt; &amp; зависает' in text
    assert 'Telegram Mini App' in text


def test_support_message_marks_pro_plan():
    tg = TelegramWebAppUser(id=222, first_name='User')
    user = SimpleNamespace(telegram_id=222, is_pro=True, pro_until=datetime(2099, 1, 1))
    settings = SimpleNamespace(admin_telegram_id=999, version='1.0.0')
    text = _support_text(tg=tg, user=user, settings=settings, kind='idea', message='Добавить экспорт', page=None)
    assert '<b>Тариф:</b> PRO' in text
    assert '💡 Идея' in text
