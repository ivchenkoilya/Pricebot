from app.bot.ai_handlers import create_ai_router
from app.config.settings import Settings
from app.services.ai import AIService


def test_ai_router_builds_with_ai_disabled():
    settings = Settings(database_url='sqlite+aiosqlite:///:memory:', openai_api_key='', ai_enabled=True)
    router = create_ai_router(AIService(settings))
    assert router.name == 'price-ai'
