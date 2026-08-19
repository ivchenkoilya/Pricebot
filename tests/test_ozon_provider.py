from decimal import Decimal

import pytest

from app.trackers.providers.ozon import OzonProvider, canonicalize_ozon_url, is_ozon_url, ozon_product_id


def test_ozon_url_helpers():
    assert is_ozon_url('https://ozon.ru/t/RhE8Ybw')
    assert is_ozon_url('https://www.ozon.ru/product/test-1708253219/?utm_source=tg')
    assert ozon_product_id('https://www.ozon.ru/product/test-1708253219/') == '1708253219'
    assert canonicalize_ozon_url('https://ozon.ru/product/test-1708253219/?page=2&utm_source=tg') == 'https://www.ozon.ru/product/test-1708253219/'


def test_ozon_visible_product_parser_prefers_normal_bank_price():
    html = '''
    <html>
      <head>
        <title>Samsung Galaxy S24 купить c доставкой на OZON по низкой цене</title>
        <meta property="og:image" content="https://cdn.example/s24.jpg">
        <link rel="canonical" href="https://www.ozon.ru/product/samsung-galaxy-s24-1708253219/?utm_source=x">
      </head>
      <body>
        <h1>Samsung Galaxy S24 8/256 ГБ</h1>
        <div>36\u2009165\u2009₽</div>
        <div>С банками</div>
        <div>37\u202f186\u202f₽</div>
        <s>78\u202f421\u202f₽</s>
        <div>С другими банками</div>
        <button>В корзину</button>
        <div>Есть дешевле или быстрее от 34\u202f937\u202f₽</div>
      </body>
    </html>
    '''
    snap = OzonProvider.parse_ozon_document(
        html,
        'https://www.ozon.ru/product/samsung-galaxy-s24-1708253219/?from=share',
    )
    assert snap.product_name == 'Samsung Galaxy S24 8/256 ГБ'
    assert snap.current_price == Decimal('37186.00')
    assert snap.old_price == Decimal('78421.00')
    assert snap.currency == 'RUB'
    assert snap.availability == 'in_stock'
    assert snap.canonical_url == 'https://www.ozon.ru/product/samsung-galaxy-s24-1708253219/'
    assert snap.confidence >= 0.9


def test_ozon_parser_does_not_take_cheaper_recommendation():
    html = '''
    <html><body>
      <h1>Наушники Sony</h1>
      <div>15 570 ₽</div>
      <div>С банками</div>
      <div>16 390 ₽</div>
      <div>С другими банками</div>
      <button>Купить сейчас</button>
      <div>Есть дешевле или быстрее от 1 364 ₽</div>
    </body></html>
    '''
    snap = OzonProvider.parse_ozon_document(html, 'https://www.ozon.ru/product/sony-1757427624/')
    assert snap.current_price == Decimal('16390.00')


@pytest.mark.asyncio
async def test_ozon_provider_supports_short_links(db):
    _database, settings = db
    provider = OzonProvider(settings)
    assert await provider.supports('https://ozon.ru/t/RhE8Ybw') is True
    assert await provider.supports('https://example.com/product') is False
