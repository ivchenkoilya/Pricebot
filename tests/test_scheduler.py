from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.database.models import Product, User, Watch
from app.scheduler.runner import PriceScheduler
from app.trackers.base import ProductSnapshot


class FakeRegistry:
    async def fetch(self, url):
        return ProductSnapshot(
            product_name='Updated', current_price=Decimal('80'), old_price=None, currency='RUB',
            availability='in_stock', canonical_url=url, source='example.com', confidence=0.99
        )


class FakeBot:
    async def send_message(self, *args, **kwargs):
        return None


@pytest.mark.asyncio
async def test_scheduler_checks_shared_product_once(db):
    database, settings = db
    async with database.session_factory() as session:
        p = Product(canonical_url='https://example.com/p', source='example.com', name='P', current_price=Decimal('100'), currency='RUB', next_check_at=datetime.utcnow()-timedelta(minutes=1))
        u1 = User(telegram_id=1)
        u2 = User(telegram_id=2)
        session.add_all([p, u1, u2])
        await session.flush()
        session.add_all([Watch(user_id=u1.id, product_id=p.id), Watch(user_id=u2.id, product_id=p.id)])
        await session.commit()
    scheduler = PriceScheduler(database, FakeRegistry(), FakeBot(), settings)
    checked = await scheduler.run_once()
    assert checked == 1
    async with database.session_factory() as session:
        product = await session.get(Product, p.id)
        assert product.current_price == Decimal('80.00')
