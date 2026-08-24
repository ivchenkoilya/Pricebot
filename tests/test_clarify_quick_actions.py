from app.bot.clarify_quick_actions import NAVIGATION_TEXTS, _plan_text
from app.bot.razberi_keyboards import BTN_INBOX, BTN_MINIAPP, BTN_PLANS, BTN_PROFILE, LEGACY_INBOX
from app.config.settings import Settings


def test_quick_plan_message_uses_current_request_packs_only():
    settings = Settings(_env_file=None)
    text = _plan_text(settings, 'FREE', 0)
    assert 'PRO · 250 ⭐' in text
    assert 'PRO MAX · 350 ⭐' in text
    assert '+50 — 50 ⭐' in text
    assert '+150 — 100 ⭐' in text
    assert '+500 — 250 ⭐' in text
    assert '+2000' not in text


def test_quick_navigation_recognizes_new_and_old_important_label():
    assert BTN_PLANS in NAVIGATION_TEXTS
    assert BTN_PROFILE in NAVIGATION_TEXTS
    assert BTN_MINIAPP in NAVIGATION_TEXTS
    assert BTN_INBOX == '⚡ Важное сейчас'
    assert BTN_INBOX in NAVIGATION_TEXTS
    assert LEGACY_INBOX in NAVIGATION_TEXTS
