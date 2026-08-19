from types import SimpleNamespace

import pytest

from app.config.settings import Settings
from app.services.page_reader import PageReadResult
from app.trackers.providers.page_ai import AIPageProvider


class FakeReader:
    async def read(self, url: str):
        return PageReadResult(
            requested_url=url,
            final_url='https://shop.example/product/123',
            title='Sony WH-1000XM6 беспроводные наушники',
            description=None,
            text='Sony WH-1000XM6 беспроводные наушники. Купить. 39 990 ₽',
            source='jina-reader',
        )


class BrokenAI:
    enabled = True

    async def analyze_page(self, *args, **kwargs):
        return None


@pytest.mark.asyncio
async def test_page_provider_keeps_readable_title_when_ai_gateway_fails():
    settings = Settings(database_url='sqlite+aiosqlite:///:memory:', openai_api_key='sk-test')
    provider = AIPageProvider(settings)
    provider.reader = FakeReader()
    provider.ai = BrokenAI()

    snapshot = await provider.fetch('https://shop.example/p/1')

    assert snapshot.product_name == 'Sony WH-1000XM6 беспроводные наушники'
    assert snapshot.current_price is None
    assert snapshot.source == 'shop.example via jina-reader'
    assert snapshot.confidence == 0.46


@pytest.mark.asyncio
async def test_page_provider_supports_public_url_even_without_ai_key():
    settings = Settings(database_url='sqlite+aiosqlite:///:memory:', openai_api_key='')
    provider = AIPageProvider(settings)
    assert await provider.supports('https://example.com/product') is True
