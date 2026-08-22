import json

import pytest
from sqlalchemy import select

from app.bot.razberi_keyboards import actions
from app.database.models import User
from app.database.razberi_models import AIUsage, Referral
from app.services.growth import GrowthService, build_referral_link, parse_start_payload
from app.webapp import webapp_api_router


def test_direct_start_is_recorded_as_direct():
    parsed = parse_start_payload('')
    assert parsed.source == 'direct'
    assert parsed.campaign is None
    assert parsed.referrer_telegram_id is None


def test_referral_payload_extracts_telegram_id():
    parsed = parse_start_payload('ref_123456789')
    assert parsed.source == 'referral'
    assert parsed.referrer_telegram_id == 123456789
    assert parsed.raw_payload == 'ref_123456789'


def test_campaign_sources_are_normalized():
    assert parse_start_payload('tiktok_august_1').source == 'tiktok'
    assert parse_start_payload('youtube_short_7').source == 'youtube'
    assert parse_start_payload('tg_channel_students').source == 'telegram'
    assert parse_start_payload('ads_launch_3').source == 'telegram_ads'


def test_referral_link_is_stable():
    assert build_referral_link('@ClarifyExampleBot', 42) == 'https://t.me/ClarifyExampleBot?start=ref_42'


def test_material_actions_include_privacy_safe_share_callback():
    keyboard = actions(77, 'voice')
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert 'share:77' in callbacks


def test_mini_app_profile_stats_route_is_registered():
    paths = {getattr(route, 'path', None) for route in webapp_api_router.routes}
    assert '/api/profile/stats' in paths


@pytest.mark.asyncio
async def test_referral_rewards_both_users_once_after_first_ai_analysis(db):
    database, settings = db
    growth = GrowthService(database, settings.model_copy(update={'referral_bonus_requests': 20}))

    async with database.sessions() as session:
        referrer = User(telegram_id=1001, username='referrer', first_name='Referrer')
        referred = User(telegram_id=1002, username='referred', first_name='Referred')
        session.add_all([referrer, referred])
        await session.commit()
        await session.refresh(referrer)
        await session.refresh(referred)
        referrer_id = referrer.id
        referred_id = referred.id

    await growth.capture_start(referred_id, 'ref_1001')
    assert await growth.sync_conversion(1002) is None

    async with database.sessions() as session:
        session.add(AIUsage(user_id=referred_id, model='test', feature='voice', input_tokens=1, output_tokens=1))
        await session.commit()

    reward = await growth.sync_conversion(1002)
    assert reward is not None
    assert reward.amount == 20
    assert reward.referrer_telegram_id == 1001
    assert reward.referred_telegram_id == 1002

    # Reward is idempotent: further middleware passes must not add bonus again.
    assert await growth.sync_conversion(1002) is None

    async with database.sessions() as session:
        referrer = await session.get(User, referrer_id)
        referred = await session.get(User, referred_id)
        referral = (
            await session.execute(select(Referral).where(Referral.referred_user_id == referred_id))
        ).scalar_one()

        assert json.loads(referrer.notification_settings or '{}')['clarify_bonus_requests'] == 20
        assert json.loads(referred.notification_settings or '{}')['clarify_bonus_requests'] == 20
        assert referral.status == 'rewarded'
        assert referral.reward_amount == 20


@pytest.mark.asyncio
async def test_existing_ai_user_cannot_become_new_referral(db):
    database, settings = db
    growth = GrowthService(database, settings)

    async with database.sessions() as session:
        referrer = User(telegram_id=2001, username='referrer2', first_name='Referrer')
        existing = User(telegram_id=2002, username='existing', first_name='Existing')
        session.add_all([referrer, existing])
        await session.flush()
        existing_id = existing.id
        session.add(AIUsage(user_id=existing_id, model='test', feature='old_use'))
        await session.commit()

    parsed = await growth.capture_start(existing_id, 'ref_2001')
    assert parsed.source == 'referral'

    async with database.sessions() as session:
        referral = (
            await session.execute(select(Referral).where(Referral.referred_user_id == existing_id))
        ).scalar_one_or_none()
    assert referral is None
