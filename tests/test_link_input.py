from decimal import Decimal

from app.bot.handlers import extract_url_from_text, strict_target_price


def test_extract_url_from_text_accepts_short_ozon_without_scheme():
    assert extract_url_from_text('Смотри ozon.ru/t/RhE8Ybw') == 'https://ozon.ru/t/RhE8Ybw'


def test_extract_url_from_text_keeps_https():
    assert extract_url_from_text('https://www.ozon.ru/product/test-1234567890/?x=1') == 'https://www.ozon.ru/product/test-1234567890/?x=1'


def test_target_price_is_strict_and_never_reads_digits_from_url():
    assert strict_target_price('30000') == Decimal('30000.00')
    assert strict_target_price('29 990 ₽') == Decimal('29990.00')
    assert strict_target_price('https://ozon.ru/t/RhE8Ybw') is None
    assert strict_target_price('цена 30000') is None
