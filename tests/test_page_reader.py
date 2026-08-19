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


def test_ozon_connection_error_page_is_not_accepted_as_product():
    reader = PageReader(_settings(page_reader_min_chars=10))
    result = PageReadResult(
        requested_url='https://ozon.ru/t/example',
        final_url='https://ozon.ru/t/example',
        title='Похоже, нет соединения',
        description=None,
        text='Похоже, нет соединения. Проверьте подключение к интернету и попробуйте ещё раз.',
        source='jina-reader',
    )
    assert reader._useful(result) is False


def test_resolved_ozon_product_url_preserves_public_slug_and_id():
    reader = PageReader(_settings())
    result = reader._from_ozon_product_url(
        'https://ozon.ru/t/example',
        'https://www.ozon.ru/product/sony-wh-1000xm6-chernyy-1234567890/',
    )
    assert result is not None
    assert result.source == 'resolved-url'
    assert result.final_url.endswith('/sony-wh-1000xm6-chernyy-1234567890/')
    assert 'Sony wh 1000xm6 chernyy' in result.title
    assert '1234567890' in result.text
    assert reader._ozon_product_id(result.final_url) == '1234567890'


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
