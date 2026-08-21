from app.bot.razberi_keyboards import (
    BTN_CLEAR,
    BTN_COMPARE,
    BTN_HELP,
    BTN_INBOX,
    BTN_MEMORY,
    BTN_MINIAPP,
    BTN_PLANS,
    BTN_PROJECTS,
    BTN_SETTINGS,
    BTN_SUPPORT,
    BTN_UNPACK,
    BTN_WRITE,
    main_menu,
)


def _texts(menu):
    return [button.text for row in menu.keyboard for button in row]


def test_main_menu_contains_current_product_sections():
    menu = main_menu('https://pricebot2-ivch.amvera.io/app/')
    assert _texts(menu) == [
        BTN_UNPACK, BTN_WRITE,
        BTN_MEMORY, BTN_INBOX,
        BTN_PROJECTS, BTN_COMPARE,
        BTN_PLANS, BTN_SUPPORT,
        BTN_SETTINGS, BTN_CLEAR,
        BTN_HELP, BTN_MINIAPP,
    ]


def test_mini_app_is_real_webapp_button_for_https_url():
    menu = main_menu('https://pricebot2-ivch.amvera.io/app/')
    mini = menu.keyboard[-1][-1]
    assert mini.text == BTN_MINIAPP
    assert mini.web_app is not None
    assert mini.web_app.url == 'https://pricebot2-ivch.amvera.io/app/'


def test_mini_app_falls_back_to_text_button_without_https():
    menu = main_menu('')
    assert menu.keyboard[-1][-1].web_app is None
