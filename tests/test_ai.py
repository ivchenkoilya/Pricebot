from types import SimpleNamespace

import pytest

from app.bot.ai_handlers import is_ai_candidate_text
from app.config.settings import Settings
from app.services.ai import AIService, ProductIntent


class FakeResponses:
    def __init__(self):
        self.kwargs = None

    async def parse(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            output_parsed=ProductIntent(
                is_product=True,
                action='find_cheaper',
                brand='Apple',
                model='iPhone 16 Pro',
                variant='256 GB black',
                normalized_name='Apple iPhone 16 Pro 256 GB black',
                search_query='Apple iPhone 16 Pro 256GB black',
                confidence=0.98,
            )
        )


class FakeClient:
    def __init__(self):
        self.responses = FakeResponses()


@pytest.mark.asyncio
async def test_ai_is_optional_without_api_key():
    settings = Settings(database_url='sqlite+aiosqlite:///:memory:', openai_api_key='', ai_enabled=True)
    service = AIService(settings)
    assert service.enabled is False
    assert await service.analyze_product_text('айфон 16 про 256') is None


@pytest.mark.asyncio
async def test_ai_uses_structured_responses_without_storage():
    settings = Settings(
        database_url='sqlite+aiosqlite:///:memory:',
        openai_api_key='',
        ai_enabled=True,
        openai_model='gpt-5-mini',
    )
    client = FakeClient()
    service = AIService(settings, client=client)
    result = await service.analyze_product_text('найди дешевле айфон 16 про 256 чёрный')

    assert result is not None
    assert result.is_product is True
    assert result.action == 'find_cheaper'
    assert result.brand == 'Apple'
    assert result.model == 'iPhone 16 Pro'
    assert client.responses.kwargs['model'] == 'gpt-5-mini'
    assert client.responses.kwargs['store'] is False
    assert client.responses.kwargs['text_format'] is ProductIntent


def test_ai_text_filter_does_not_intercept_deterministic_flows():
    assert is_ai_candidate_text('iPhone 16 Pro 256 чёрный') is True
    assert is_ai_candidate_text('найди дешевле Sony WH-1000XM6') is True
    assert is_ai_candidate_text('https://ozon.ru/t/RhE8Ybw') is False
    assert is_ai_candidate_text('ozon.ru/t/RhE8Ybw') is False
    assert is_ai_candidate_text('30000') is False
    assert is_ai_candidate_text('10%') is False
    assert is_ai_candidate_text('🔔 Мои товары') is False
    assert is_ai_candidate_text('/status') is False
