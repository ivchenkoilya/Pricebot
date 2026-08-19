from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

CURRENCY_MAP = {'₽': 'RUB', 'руб': 'RUB', 'руб.': 'RUB', '$': 'USD', '€': 'EUR', '₸': 'KZT', '₴': 'UAH'}


def parse_price(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value)).quantize(Decimal('0.01'))
        except InvalidOperation:
            return None
    text = str(value).replace('\xa0', ' ').strip()
    cleaned = re.sub(r'[^0-9,\.\s]', '', text).strip()
    if not cleaned:
        return None
    cleaned = cleaned.replace(' ', '')
    if ',' in cleaned and '.' in cleaned:
        if cleaned.rfind(',') > cleaned.rfind('.'):
            cleaned = cleaned.replace('.', '').replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
    elif ',' in cleaned:
        tail = cleaned.rsplit(',', 1)[-1]
        cleaned = cleaned.replace(',', '.') if len(tail) <= 2 else cleaned.replace(',', '')
    elif cleaned.count('.') > 1:
        cleaned = cleaned.replace('.', '')
    try:
        amount = Decimal(cleaned).quantize(Decimal('0.01'))
    except InvalidOperation:
        return None
    if amount <= 0 or amount > Decimal('1000000000'):
        return None
    return amount


def format_money(value: Decimal | None, currency: str | None = 'RUB') -> str:
    if value is None:
        return 'цена не определена'
    number = f'{value:,.0f}'.replace(',', ' ')
    suffix = {'RUB': '₽', 'USD': '$', 'EUR': '€', 'KZT': '₸'}.get((currency or '').upper(), currency or '')
    return f'{number} {suffix}'.strip()


def percent_change(old: Decimal | None, new: Decimal | None) -> Decimal | None:
    if old is None or new is None or old <= 0:
        return None
    return ((new - old) / old * Decimal('100')).quantize(Decimal('0.1'))
