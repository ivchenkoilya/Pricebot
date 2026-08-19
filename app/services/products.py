from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings
from app.database.models import PriceHistory, Product, ProviderError as ProviderErrorModel, User, Watch
from app.trackers.base import ProductSnapshot
from app.trackers.registry import ProviderRegistry
from app.utils.url import normalize_url

logger = logging.getLogger(__name__)


class WatchLimitError(RuntimeError):
    pass


async def get_or_create_product_from_url(session: AsyncSession, registry: ProviderRegistry, settings: Settings, url: str) -> tuple[Product, ProductSnapshot | None, str | None]:
    normalized = normalize_url(url)
    existing = (await session.execute(select(Product).where(Product.canonical_url == normalized))).scalar_one_or_none()
    try:
        snapshot = await registry.fetch(normalized)
        canonical = normalize_url(snapshot.canonical_url)
        product = (await session.execute(select(Product).where(Product.canonical_url == canonical))).scalar_one_or_none()
        if product is None:
            product = existing or Product(canonical_url=canonical, source=snapshot.source, name=snapshot.product_name)
            if existing is None:
                session.add(product)
        product.canonical_url = canonical
        product.source = snapshot.source
        product.name = snapshot.product_name
        product.image_url = snapshot.image_url
        product.currency = snapshot.currency
        product.seller = snapshot.seller
        product.old_price = snapshot.old_price
        product.current_price = snapshot.current_price
        product.availability = snapshot.availability
        product.last_checked_at = snapshot.checked_at
        product.next_check_at = snapshot.checked_at + timedelta(hours=settings.check_interval_free_hours)
        product.check_interval_minutes = settings.check_interval_free_hours * 60

        # AI page-reading may successfully identify the product while the store
        # still withholds a reliable price. Preserve that useful identity, but do
        # not mark the price tracker healthy until a deterministic provider has
        # actually confirmed a current price.
        has_price = snapshot.current_price is not None
        product.check_status = 'ok' if has_price else 'degraded'
        product.failure_count = 0
        product.last_error = None if has_price else 'Страница прочитана, но цена пока не подтверждена provider-парсером'
        await session.flush()
        session.add(
            PriceHistory(
                product_id=product.id,
                price=snapshot.current_price,
                old_price=snapshot.old_price,
                availability=snapshot.availability,
                checked_at=snapshot.checked_at,
            )
        )
        await session.commit()
        await session.refresh(product)
        return product, snapshot, None if has_price else product.last_error
    except Exception as exc:
        host = urlsplit(normalized).hostname or 'unknown'
        product = existing
        if product is None:
            product = Product(canonical_url=normalized, source=host, name=host, availability='unknown', check_status='degraded', failure_count=1, last_error=str(exc)[:1000], next_check_at=datetime.utcnow() + timedelta(hours=settings.check_interval_free_hours), check_interval_minutes=settings.check_interval_free_hours * 60)
            session.add(product)
            await session.flush()
        else:
            product.failure_count += 1
            product.check_status = 'degraded'
            product.last_error = str(exc)[:1000]
        session.add(ProviderErrorModel(source='generic', url_host=host, error=str(exc)[:1500]))
        await session.commit()
        await session.refresh(product)
        logger.warning('provider failure host=%s error=%s', host, exc.__class__.__name__)
        return product, None, str(exc)


async def active_watch_count(session: AsyncSession, user_id: int) -> int:
    return int((await session.execute(select(func.count(Watch.id)).where(Watch.user_id == user_id, Watch.active.is_(True)))).scalar_one())


def user_is_pro(user: User) -> bool:
    return bool(user.is_pro and (user.pro_until is None or user.pro_until > datetime.utcnow()))


async def create_or_activate_watch(session: AsyncSession, user: User, product: Product, settings: Settings) -> Watch:
    watch = (await session.execute(select(Watch).where(Watch.user_id == user.id, Watch.product_id == product.id))).scalar_one_or_none()
    if watch and watch.active:
        return watch
    count = await active_watch_count(session, user.id)
    limit = settings.pro_watch_limit if user_is_pro(user) else (user.free_limit or settings.free_watch_limit)
    if count >= limit:
        raise WatchLimitError(f'Лимит отслеживания: {limit}')
    if watch is None:
        watch = Watch(user_id=user.id, product_id=product.id, baseline_price=product.current_price, notify_any_drop=True, notify_new_low=user_is_pro(user), active=True)
        session.add(watch)
    else:
        watch.active = True
        watch.baseline_price = watch.baseline_price or product.current_price
    interval_h = settings.check_interval_pro_hours if user_is_pro(user) else settings.check_interval_free_hours
    if product.check_interval_minutes > interval_h * 60:
        product.check_interval_minutes = interval_h * 60
        product.next_check_at = datetime.utcnow() + timedelta(hours=interval_h)
    await session.commit()
    await session.refresh(watch)
    return watch


async def set_target_price(session: AsyncSession, user_id: int, product_id: int, target: Decimal) -> Watch | None:
    watch = (await session.execute(select(Watch).where(Watch.user_id == user_id, Watch.product_id == product_id, Watch.active.is_(True)))).scalar_one_or_none()
    if watch:
        watch.target_price = target
        await session.commit()
    return watch


async def product_stats(session: AsyncSession, product_id: int) -> dict:
    rows = (await session.execute(select(PriceHistory.price, PriceHistory.checked_at).where(PriceHistory.product_id == product_id, PriceHistory.is_test.is_(False), PriceHistory.price.is_not(None)).order_by(PriceHistory.checked_at.asc()))).all()
    prices = [r[0] for r in rows if r[0] is not None]
    now = datetime.utcnow()

    def change_since(days: int):
        if not rows:
            return None
        cutoff = now - timedelta(days=days)
        old = next((price for price, checked in rows if checked >= cutoff and price is not None), None)
        cur = prices[-1] if prices else None
        if old is None or cur is None or old == 0:
            return None
        return ((cur - old) / old * Decimal('100')).quantize(Decimal('0.1'))

    return {'min': min(prices) if prices else None, 'max': max(prices) if prices else None, 'current': prices[-1] if prices else None, 'days': max(0, (now - rows[0][1]).days) if rows else 0, 'change_7d': change_since(7), 'change_30d': change_since(30)}
