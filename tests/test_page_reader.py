from decimal import Decimal

import pytest

from app.config.settings import Settings
from app.services.ai import PageInsight
from app.services.page_reader import PageReadResult, PageReader
from app.trackers.providers.page_ai import AIPageProvider


def _settings(**kwargs):
    return Settings(database_url='sqlite+aiosqlite:///:memory:', **kwargs)


def test_direct_page_reader_extracts_product_context():
    reader = PageReader(_settings())
    html = '''
    <html><head>
      <title>Fallback title</title>
      <meta property="og:title" content="Sony WH-1000XM6 Black">
      <meta name="description" content="Wireless headphones">
      <script type="application/ld+json">{"@type":"Product","name":"Sony WH-1000XM6"}</script>
    </head><body>
      <h1>Sony WH-1000XM6 Black</h1>
      <div>Цена 39 990 ₽</div><button>В корзину</button>
      <script>ignore me</script>
    </body></html>
    '''
    result = reader._from_html('https://shop.example/item', 'https://shop.example/item', html)
    assert result.title == 'Sony WH-1000XM6 Black'
    assert 'Wireless headphones' in result.text
    assert '39 990 ₽' in result.text
    assert 'Product' in result.text
    assert 'ignore me' not in result.text


class FakeReader:
    async def read(self, url):
        return PageReadResult(
            requested_url=url,
            final_url='https://www.ozon.ru/product/sony-wh-1000xm6-123456789/',
            title='Sony WH-1000XM6',
            description=None,
            text='Sony WH-1000XM6 39 990 ₽ В корзину',
            source='jina-reader',
        )


class FakeAI:
    enabled = True

    async def analyze_page(self, url, title, page_text):
        return PageInsight(
            is_product=True,
            product_name='Sony WH-1000XM6',
            brand='Sony',
            model='WH-1000XM6',
            observed_price_texts=['39 990 ₽'],
            availability_text='В корзину',
            confidence=0.97,
        )


@pytest.mark.asyncio
async def test_ai_page_provider_identifies_product_but_never_invents_price():
    provider = AIPageProvider(_settings(openai_api_key='sk-test'))
    provider.reader = FakeReader()
    provider.ai = FakeAI()

    snapshot = await provider.fetch('https://ozon.ru/t/example')
    assert snapshot.product_name == 'Sony WH-1000XM6'
    assert snapshot.current_price is None
    assert snapshot.old_price is None
    assert snapshot.availability == 'in_stock'
    assert snapshot.canonical_url.startswith('https://www.ozon.ru/product/')
    assert snapshot.confidence <= 0.84


def test_page_insight_price_mentions_are_observations_not_decimal_price():
    insight = PageInsight(
        is_product=True,
        product_name='Phone',
        observed_price_texts=['59 990 ₽', '79 990 ₽'],
        confidence=0.8,
    )
    assert insight.observed_price_texts == ['59 990 ₽', '79 990 ₽']
    # The fallback model has no authoritative numeric current_price field.
    assert not hasattr(insight, 'current_price')
