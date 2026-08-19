from pathlib import Path

import pytest
from sqlalchemy import select

from app.config.settings import Settings
from app.database.models import User
from app.database.session import Database


@pytest.mark.asyncio
async def test_sqlite_persists_across_database_reopen(tmp_path: Path):
    path = tmp_path / 'price.db'
    settings = Settings(database_url=f'sqlite+aiosqlite:///{path}', bot_token='x')
    db1 = Database(settings)
    await db1.init()
    async with db1.session_factory() as session:
        session.add(User(telegram_id=42))
        await session.commit()
    await db1.close()

    db2 = Database(settings)
    await db2.init()
    async with db2.session_factory() as session:
        user = (await session.execute(select(User).where(User.telegram_id == 42))).scalar_one()
        assert user.telegram_id == 42
    await db2.close()
