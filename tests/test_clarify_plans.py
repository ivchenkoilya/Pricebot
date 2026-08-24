import json
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.bot.clarify_chat import _looks_like_clear_materials, _looks_like_plans
from app.config.settings import Settings
from app.services.core import bonus_requests, clarify_plan, plan_daily_ai_limit
from app.services.usage_guard import plan_monthly_ai_limit
from app.webapp.plans_v2 import _catalog, _packs, _product


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
    assert plan_daily_ai_limit(pro, settings) == 100
    assert plan_daily_ai_limit(max_user, settings) == 250
    assert plan_daily_ai_limit(owner, settings) is None
    assert plan_monthly_ai_limit(pro, settings) == 1500
    assert plan_monthly_ai_limit(max_user, settings) == 4000
    assert bonus_requests(max_user) == 500


def test_catalog_and_request_packs_match_prelaunch_prices():
    settings = Settings(_env_file=None)
    catalog = {item['code']: item for item in _catalog(settings)}
    packs = _packs(settings)

    assert settings.pro_stars_price == 250
    assert settings.max_stars_price == 350
    assert catalog['PRO']['price'] == 250
    assert catalog['MAX']['daily_requests'] == 250
    assert [item['requests'] for item in packs] == [50, 150, 500]
    assert [item['price'] for item in packs] == [50, 100, 250]
    assert _product(settings, 'pack150')['price'] == settings.request_pack_150_stars
    assert _product(settings, 'pack500')['price'] == settings.request_pack_500_stars
    assert _product(settings, 'pack2000') is None


def test_management_questions_are_not_material_followups():
    assert _looks_like_clear_materials('Как удалить все материалы?')
    assert _looks_like_clear_materials('Хочу полностью очистить Memory')
    assert _looks_like_plans('Какие есть тарифы?')
    assert _looks_like_plans('Как докупить запросы?')
