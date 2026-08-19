from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Notification, PriceHistory, Product, ProviderError, User, Watch


async def owner_stats(session: AsyncSession) -> dict[str, int | float]:
    now = datetime.utcnow()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    checks_today = int((await session.execute(select(func.count(PriceHistory.id)).where(PriceHistory.checked_at >= midnight))).scalar_one())
    failures_today = int((await session.execute(select(func.count(ProviderError.id)).where(ProviderError.created_at >= midnight))).scalar_one())
    attempts = checks_today + failures_today
    success_rate = round(checks_today / attempts * 100, 1) if attempts else 100.0
    return {
        'users_total': int((await session.execute(select(func.count(User.id)))).scalar_one()),
        'active_users_7d': int((await session.execute(select(func.count(User.id)).where(User.last_active_at >= now - timedelta(days=7)))).scalar_one()),
        'tracked_products': int((await session.execute(select(func.count(Product.id)))).scalar_one()),
        'active_watches': int((await session.execute(select(func.count(Watch.id)).where(Watch.active.is_(True)))).scalar_one()),
        'checks_today': checks_today,
        'alerts_sent': int((await session.execute(select(func.count(Notification.id)).where(Notification.sent_at.is_not(None)))).scalar_one()),
        'provider_success_rate': success_rate,
        'pro_users': int((await session.execute(select(func.count(User.id)).where(User.is_pro.is_(True)))).scalar_one()),
    }
