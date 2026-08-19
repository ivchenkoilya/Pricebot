from decimal import Decimal

from app.utils.money import parse_price, percent_change


def test_parse_common_prices():
    assert parse_price('34 990 ₽') == Decimal('34990.00')
    assert parse_price('1 299,90 руб.') == Decimal('1299.90')
    assert parse_price('not a price') is None


def test_percent_change():
    assert percent_change(Decimal('100'), Decimal('90')) == Decimal('-10.0')
