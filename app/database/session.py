from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import Settings
from app.database.models import Base


class Database:
    def __init__(self, settings: Settings):
        self.engine: AsyncEngine = create_async_engine(settings.database_url, pool_pre_ping=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)

    async def init(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def ping(self) -> bool:
        from sqlalchemy import text
        try:
            async with self.session_factory() as session:
                await session.execute(text('SELECT 1'))
            return True
        except Exception:
            return False

    async def close(self) -> None:
        await self.engine.dispose()
