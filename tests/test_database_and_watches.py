from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.database.models import PriceHistory, Product, Watch
from app.services.products import WatchLimitError, create_or_activate_watch, product_stats, set_target_price
from app.services.users import get_or_create_user


@pytest.mark.asyncio
async def test_product_watch_target_and_free_limit(db):
    database, settings = db
    settings.free_watch_limit = 1
    async with database.session_factory() as session:
        tg = SimpleNamespace(id=100, username='u', first_name='Ilya')
        user = await get_or_create_user(session, tg, settings)
        p1 = Product(canonical_url='https://example.com/1', source='example.com', name='One', current_price=Decimal('100.00'), currency='RUB')
        p2 = Product(canonical_url='https://example.com/2', source='example.com', name='Two', current_price=Decimal('200.00'), currency='RUB')
        session.add_all([p1, p2])
        await session.commit()
        watch = await create_or_activate_watch(session, user, p1, settings)
        assert watch.baseline_price == Decimal('100.00')
        await set_target_price(session, user.id, p1.id, Decimal('90.00'))
        refreshed = await session.get(Watch, watch.id)
        assert refreshed.target_price == Decimal('90.00')
        with pytest.raises(WatchLimitError):
            await create_or_activate_watch(session, user, p2, settings)


@pytest.mark.asyncio
async def test_price_history_uses_own_history_not_store_discount(db):
    database, settings = db
    async with database.session_factory() as session:
        p = Product(canonical_url='https://example.com/p', source='example.com', name='P', current_price=Decimal('29990'), old_price=Decimal('50000'), currency='RUB')
        session.add(p)
        await session.flush()
        session.add_all([
            PriceHistory(product_id=p.id, price=Decimal('29990'), old_price=Decimal('50000'), availability='in_stock'),
            PriceHistory(product_id=p.id, price=Decimal('29990'), old_price=Decimal('50000'), availability='in_stock'),
        ])
        await session.commit()
        stats = await product_stats(session, p.id)
        assert stats['min'] == Decimal('29990.00')
        assert stats['max'] == Decimal('29990.00')
        assert stats['change_7d'] == Decimal('0.0')


@pytest.mark.asyncio
async def test_pro_limit_is_configurable_and_higher_than_free(db):
    database, settings = db
    settings.free_watch_limit = 1
    settings.pro_watch_limit = 2
    async with database.session_factory() as session:
        tg = SimpleNamespace(id=101, username='pro', first_name='Pro')
        user = await get_or_create_user(session, tg, settings)
        user.is_pro = True
        now = datetime.utcnow()
        user.pro_until = now.replace(year=now.year + 1)
        products = [
            Product(canonical_url=f'https://example.com/pro-{i}', source='example.com', name=f'P{i}', current_price=Decimal('100.00'), currency='RUB')
            for i in range(3)
        ]
        session.add_all(products)
        await session.commit()
        await create_or_activate_watch(session, user, products[0], settings)
        await create_or_activate_watch(session, user, products[1], settings)
        with pytest.raises(WatchLimitError):
            await create_or_activate_watch(session, user, products[2], settings)
