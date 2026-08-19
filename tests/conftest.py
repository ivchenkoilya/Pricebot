import pytest_asyncio

from app.config.settings import Settings
from app.database.session import Database


@pytest_asyncio.fixture
async def db():
    settings = Settings(database_url='sqlite+aiosqlite:///:memory:', bot_token='test')
    database = Database(settings)
    await database.init()
    try:
        yield database, settings
    finally:
        await database.close()
