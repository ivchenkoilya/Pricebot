from __future__ import annotations

import logging
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config.settings import Settings
from app.database.models import PriceHistory, Product, ProviderError as ProviderErrorModel, Watch
from app.database.session import Database
from app.services.alerts import evaluate_and_send
from app.services.products import user_is_pro
from app.trackers.registry import ProviderRegistry

logger = logging.getLogger(__name__)


class PriceScheduler:
    def __init__(self, db: Database, registry: ProviderRegistry, bot: Bot, settings: Settings):
        self.db = db
        self.registry = registry
        self.bot = bot
        self.settings = settings
        self.running = False
        self.last_run_at: datetime | None = None
        self.last_error: str | None = None

    async def _effective_interval_minutes(self, session: AsyncSession, product_id: int) -> int:
        watches = (await session.execute(select(Watch).where(Watch.product_id == product_id, Watch.active.is_(True)).options(selectinload(Watch.user)))).scalars().all()
        if any(user_is_pro(w.user) for w in watches):
            return self.settings.check_interval_pro_hours * 60
        return self.settings.check_interval_free_hours * 60

    async def check_product(self, session: AsyncSession, product: Product) -> int:
        previous_price = product.current_price
        previous_availability = product.availability
        now = datetime.utcnow()
        try:
            snapshot = await self.registry.fetch(product.canonical_url)
            product.name = snapshot.product_name
            product.image_url = snapshot.image_url
            product.currency = snapshot.currency or product.currency
            product.seller = snapshot.seller
            product.old_price = snapshot.old_price
            product.current_price = snapshot.current_price
            product.availability = snapshot.availability
            product.last_checked_at = snapshot.checked_at
            product.check_status = 'ok'
            product.failure_count = 0
            product.last_error = None
            product.check_interval_minutes = await self._effective_interval_minutes(session, product.id)
            product.next_check_at = now + timedelta(minutes=product.check_interval_minutes)
            session.add(PriceHistory(product_id=product.id, price=snapshot.current_price, old_price=snapshot.old_price, availability=snapshot.availability, checked_at=snapshot.checked_at))
            await session.commit()
            alerts = await evaluate_and_send(session, self.bot, product, previous_price, previous_availability, self.settings)
            logger.info('provider success source=%s product_id=%s alerts=%s', product.source, product.id, alerts)
            return alerts
        except Exception as exc:
            product.failure_count += 1
            product.check_status = 'degraded' if product.failure_count < self.settings.max_provider_failures else 'failed'
            product.last_error = str(exc)[:1000]
            backoff = min(product.check_interval_minutes * max(1, product.failure_count), 24 * 60 * 7)
            product.next_check_at = now + timedelta(minutes=backoff)
            host = urlsplit(product.canonical_url).hostname or 'unknown'
            session.add(ProviderErrorModel(source=product.source, url_host=host, error=str(exc)[:1500]))
            await session.commit()
            logger.warning('provider failure product_id=%s count=%s type=%s', product.id, product.failure_count, exc.__class__.__name__)
            return 0

    async def run_once(self) -> int:
        if self.running:
            return 0
        self.running = True
        checked = 0
        try:
            async with self.db.session_factory() as session:
                now = datetime.utcnow()
                products = (await session.execute(
                    select(Product)
                    .join(Watch, Watch.product_id == Product.id)
                    .where(Watch.active.is_(True), (Product.next_check_at.is_(None)) | (Product.next_check_at <= now))
                    .distinct()
                    .order_by(Product.next_check_at.asc())
                    .limit(self.settings.provider_batch_size)
                )).scalars().all()
                for product in products:
                    await self.check_product(session, product)
                    checked += 1
            self.last_run_at = datetime.utcnow()
            self.last_error = None
            return checked
        except Exception as exc:
            self.last_error = str(exc)
            logger.exception('scheduler run failed')
            return checked
        finally:
            self.running = False

    async def loop(self) -> None:
        import asyncio
        logger.info('scheduler started tick=%ss', self.settings.scheduler_tick_seconds)
        while True:
            await self.run_once()
            await asyncio.sleep(self.settings.scheduler_tick_seconds)
