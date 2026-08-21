from app.bot.clarify_support import _admin_reply_keyboard, _user_reply_keyboard
from app.webapp.support import _reply_keyboard


def _callback(markup):
    return markup.inline_keyboard[0][0].callback_data


def test_admin_can_reply_to_bot_support_ticket():
    markup = _admin_reply_keyboard(123456789)
    assert _callback(markup) == 'supportreply:123456789'
    assert 'Ответить пользователю' in markup.inline_keyboard[0][0].text


def test_admin_can_reply_to_mini_app_support_ticket():
    markup = _reply_keyboard(987654321)
    assert _callback(markup) == 'supportreply:987654321'


def test_user_can_continue_support_dialogue():
    markup = _user_reply_keyboard()
    assert _callback(markup) == 'support:open'
    assert 'Ответить поддержке' in markup.inline_keyboard[0][0].text
