from app.bot.razberi_keyboards import actions
from app.services.growth import build_referral_link, parse_start_payload


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
