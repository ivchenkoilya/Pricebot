from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ai.conversation import extract_urls, text_without_urls
from app.ai.schemas import AnalysisResult
from app.bot.razberi_keyboards import quick_webapp_url
from app.config.settings import Settings
from app.database.models import User
from app.database.razberi_models import AIUsage
from app.services.growth_prompt import GrowthPromptService
from app.webapp.plans_v2 import _packs


def test_prelaunch_plan_defaults_are_economically_bounded():
    settings = Settings(_env_file=None)
    assert settings.pro_stars_price == 250
    assert settings.max_stars_price == 350
    assert settings.pro_daily_ai_limit == 100
    assert settings.max_daily_ai_limit == 250
    assert settings.pro_monthly_ai_limit == 1500
    assert settings.max_monthly_ai_limit == 4000
    assert settings.media_download_enabled is False


def test_request_packs_are_50_150_500_and_legacy_2000_is_gone():
    settings = Settings(_env_file=None)
    packs = _packs(settings)
    assert [(item['requests'], item['price']) for item in packs] == [
        (50, 50),
        (150, 100),
        (500, 250),
    ]


def test_telegram_output_uses_safe_task_bullets():
    result = AnalysisResult(summary='Готово', tasks=['Сделать первый шаг'])
    full = result.to_telegram()
    compact = result.to_compact_telegram()
    assert '• Сделать первый шаг' in full
    assert '• Сделать первый шаг' in compact
    assert '☐' not in full + compact


def test_plain_domain_is_routed_as_a_real_url():
    assert extract_urls('Проверь vk.ru пожалуйста') == ['https://vk.ru/']
    assert extract_urls('Открой youtube.com/watch?v=abc') == ['https://youtube.com/watch?v=abc']
    assert text_without_urls('Проверь vk.ru пожалуйста') == 'Проверь пожалуйста'


def test_webapp_keyboard_link_keeps_deep_page_and_cache_buster():
    url = quick_webapp_url('https://pricebot2-ivch.amvera.io/app/', 'profile')
    assert 'page=profile' in url
    assert 'launch=keyboard' in url
    assert '20260824-prelaunch1' in url


@pytest.mark.asyncio
async def test_referral_prompt_starts_on_third_success_and_has_cooldown(db):
    database, base_settings = db
    settings = base_settings.model_copy(update={
        'referral_prompt_first_success': 3,
        'referral_prompt_every_successes': 5,
        'referral_prompt_cooldown_days': 3,
        'referral_prompt_after_click_days': 7,
    })
    growth = GrowthPromptService(database, settings)

    async with database.sessions() as session:
        user = User(telegram_id=7001, username='prompt-user', first_name='Prompt')
        session.add(user)
        await session.flush()
        user_id = user.id
        session.add_all([
            AIUsage(user_id=user_id, model='test', feature='text'),
            AIUsage(user_id=user_id, model='test', feature='voice'),
        ])
        await session.commit()

    assert await growth.referral_prompt_due(7001) is False

    async with database.sessions() as session:
        session.add(AIUsage(user_id=user_id, model='test', feature='image'))
        await session.commit()

    assert await growth.referral_prompt_due(7001) is True
    assert await growth.referral_prompt_due(7001) is False

    await growth.mark_referral_prompt_clicked(user_id)
    async with database.sessions() as session:
        session.add_all([
            AIUsage(user_id=user_id, model='test', feature=f'text-{i}')
            for i in range(5)
        ])
        await session.commit()

    # Enough successes exist, but clicking the invite CTA suppresses it for a week.
    assert await growth.referral_prompt_due(7001) is False
