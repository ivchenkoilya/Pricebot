import json
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.bot.clarify_chat import _looks_like_clear_materials, _looks_like_plans
from app.config.settings import Settings
from app.services.core import bonus_requests, clarify_plan, plan_daily_ai_limit
from app.webapp.api import _catalog, _packs, _product


def _user(*, active=False, meta=None, telegram_id=123):
    return SimpleNamespace(
        telegram_id=telegram_id,
        is_pro=active,
        pro_until=datetime.utcnow() + timedelta(days=10) if active else None,
        notification_settings=json.dumps(meta or {}),
    )


def test_plan_helpers_support_free_pro_max_and_bonus():
    settings = Settings(_env_file=None, admin_telegram_id=999)
    free = _user()
    pro = _user(active=True, meta={'clarify_plan': 'PRO'})
    max_user = _user(active=True, meta={'clarify_plan': 'MAX', 'clarify_bonus_requests': 500})
    owner = _user(active=True, telegram_id=999)

    assert clarify_plan(free, settings) == 'FREE'
    assert clarify_plan(pro, settings) == 'PRO'
    assert clarify_plan(max_user, settings) == 'MAX'
    assert clarify_plan(owner, settings) == 'OWNER'
    assert plan_daily_ai_limit(max_user, settings) == settings.max_daily_ai_limit
    assert plan_daily_ai_limit(owner, settings) is None
    assert bonus_requests(max_user) == 500


def test_catalog_and_request_packs_match_prices():
    settings = Settings(_env_file=None)
    catalog = _catalog(settings)
    packs = _packs(settings)
    assert catalog['pro']['price'] == settings.pro_stars_price
    assert catalog['max']['daily_requests'] == settings.max_daily_ai_limit
    assert [item['requests'] for item in packs] == [100, 500, 2000]
    assert _product(settings, 'pack500')['price'] == settings.request_pack_500_stars


def test_management_questions_are_not_material_followups():
    assert _looks_like_clear_materials('Как удалить все материалы?')
    assert _looks_like_clear_materials('Хочу полностью очистить Memory')
    assert _looks_like_plans('Какие есть тарифы?')
    assert _looks_like_plans('Как докупить запросы?')
