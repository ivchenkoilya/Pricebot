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


def test_profile_is_real_webapp_button_for_https_url():
    menu = main_menu('https://pricebot2-ivch.amvera.io/app/')
    profile = menu.keyboard[1][1]
    assert profile.text == BTN_PROFILE
    assert profile.web_app is not None
    parsed = urlsplit(profile.web_app.url)
    assert (parsed.scheme, parsed.netloc, parsed.path) == ('https', 'pricebot2-ivch.amvera.io', '/app/')
    query = parse_qs(parsed.query)
    assert query.get('launch') == ['keyboard']
    assert query.get('page') == ['profile']
    assert query.get('v')


def test_more_menu_keeps_advanced_features_reachable():
    menu = more_menu('https://pricebot2-ivch.amvera.io/app/')
    assert _texts(menu) == [
        BTN_INBOX, BTN_PROJECTS,
        BTN_COMPARE, BTN_SUPPORT,
        BTN_SETTINGS, BTN_CLEAR,
        BTN_HELP, BTN_MINIAPP,
        BTN_BACK,
    ]
    mini = menu.keyboard[3][1]
    assert mini.web_app is not None
    query = parse_qs(urlsplit(mini.web_app.url).query)
    assert query.get('page') == ['home']


def test_webapp_buttons_fall_back_to_text_without_https():
    menu = main_menu('')
    assert menu.keyboard[1][1].web_app is None
    advanced = more_menu('')
    assert advanced.keyboard[3][1].web_app is None
