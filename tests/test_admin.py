from app.bot.handlers import _admin
from app.config.settings import Settings


def test_admin_permission_optional():
    no_admin = Settings(bot_token='x', database_url='sqlite+aiosqlite:///:memory:', admin_telegram_id=None)
    assert _admin(1, no_admin) is False
    with_admin = Settings(bot_token='x', database_url='sqlite+aiosqlite:///:memory:', admin_telegram_id=123)
    assert _admin(123, with_admin) is True
    assert _admin(124, with_admin) is False
