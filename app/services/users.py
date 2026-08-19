from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings
from app.database.models import MetricEvent, User


async def get_or_create_user(session: AsyncSession, telegram_user, settings: Settings) -> User:
    stmt = select(User).where(User.telegram_id == int(telegram_user.id))
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        user = User(
            telegram_id=int(telegram_user.id),
            username=getattr(telegram_user, 'username', None),
            first_name=getattr(telegram_user, 'first_name', None),
            timezone=settings.default_timezone,
        )
        session.add(user)
        await session.flush()
        session.add(MetricEvent(user_id=user.id, event='user_created'))
    else:
        user.username = getattr(telegram_user, 'username', None)
        user.first_name = getattr(telegram_user, 'first_name', None)
        user.last_active_at = datetime.utcnow()
    await session.commit()
    return user


async def record_metric(session: AsyncSession, user_id: int | None, event: str) -> None:
    session.add(MetricEvent(user_id=user_id, event=event))
    await session.commit()
