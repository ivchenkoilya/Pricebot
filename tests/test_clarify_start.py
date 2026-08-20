from pathlib import Path

from app.bot.clarify_start import _telegram_photo_bytes


def test_start_banner_is_valid_jpeg_payload():
    banner = Path(__file__).resolve().parents[1] / 'assets' / 'clarify_banner.jpg.b64'
    payload = _telegram_photo_bytes(banner)
    assert payload[:2] == b'\xff\xd8'
    assert payload[-2:] == b'\xff\xd9'
    assert len(payload) > 8_000
