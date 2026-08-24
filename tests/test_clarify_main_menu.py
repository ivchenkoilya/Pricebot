from urllib.parse import parse_qs, urlsplit

from app.bot.razberi_keyboards import (
    BTN_BACK,
    BTN_CLEAR,
    BTN_COMPARE,
    BTN_HELP,
    BTN_INBOX,
    BTN_MEMORY,
    BTN_MINIAPP,
    BTN_MORE,
    BTN_PLANS,
    BTN_PROFILE,
    BTN_PROJECTS,
    BTN_SETTINGS,
    BTN_SUPPORT,
    BTN_UNPACK,
    BTN_WRITE,
    main_menu,
    more_menu,
    quick_webapp_url,
)


def _texts(menu):
    return [button.text for row in menu.keyboard for button in row]


def test_main_menu_contains_only_core_product_actions():
    menu = main_menu('https://pricebot2-ivch.amvera.io/app/')
    assert _texts(menu) == [
        BTN_UNPACK, BTN_WRITE,
        BTN_MEMORY, BTN_PROFILE,
        BTN_PLANS, BTN_MORE,
    ]


def test_profile_quick_button_is_text_backed_to_avoid_stale_android_webview():
    menu = main_menu('https://pricebot2-ivch.amvera.io/app/')
    profile = menu.keyboard[1][1]
    assert profile.text == BTN_PROFILE
    assert profile.web_app is None


def test_fresh_inline_webapp_url_keeps_profile_deep_link_and_cache_buster():
    url = quick_webapp_url('https://pricebot2-ivch.amvera.io/app/', 'profile')
    parsed = urlsplit(url)
    assert (parsed.scheme, parsed.netloc, parsed.path) == ('https', 'pricebot2-ivch.amvera.io', '/app/')
    query = parse_qs(parsed.query)
    assert query.get('launch') == ['keyboard']
    assert query.get('page') == ['profile']
    assert query.get('v') == ['20260824-prelaunch2']


def test_more_menu_keeps_advanced_features_reachable_without_direct_webapp_button():
    menu = more_menu('https://pricebot2-ivch.amvera.io/app/')
    assert _texts(menu) == [
        BTN_INBOX, BTN_PROJECTS,
        BTN_COMPARE, BTN_SUPPORT,
        BTN_SETTINGS, BTN_CLEAR,
        BTN_HELP, BTN_MINIAPP,
        BTN_BACK,
    ]
    mini = menu.keyboard[3][1]
    assert mini.text == BTN_MINIAPP
    assert mini.web_app is None


def test_quick_webapp_url_normalizes_old_amvera_host():
    url = quick_webapp_url('http://pricebot2.ivch.amvera.io', 'home')
    parsed = urlsplit(url)
    assert parsed.scheme == 'https'
    assert parsed.netloc == 'pricebot2-ivch.amvera.io'
    assert parsed.path == '/app/'
    query = parse_qs(parsed.query)
    assert query.get('page') == ['home']
