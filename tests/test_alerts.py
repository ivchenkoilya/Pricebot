from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.database.models import Notification, PriceHistory, Product, User, Watch
from app.services.alerts import evaluate_and_send


class FakeBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, chat_id, text, reply_markup=None):
        self.messages.append((chat_id, text))


@pytest.mark.asyncio
async def test_price_drop_alert_and_dedup(db):
    database, settings = db
    bot = FakeBot()
    async with database.session_factory() as session:
        user = User(telegram_id=123, username='x', first_name='x')
        product = Product(canonical_url='https://example.com/p', source='example.com', name='Headphones', current_price=Decimal('90'), currency='RUB', availability='in_stock')
        session.add_all([user, product])
        await session.flush()
        watch = Watch(user_id=user.id, product_id=product.id, baseline_price=Decimal('100'), notify_any_drop=True, active=True)
        session.add(watch)
        session.add(PriceHistory(product_id=product.id, price=Decimal('100'), availability='in_stock'))
        await session.commit()
        sent1 = await evaluate_and_send(session, bot, product, Decimal('100'), 'in_stock', settings)
        sent2 = await evaluate_and_send(session, bot, product, Decimal('100'), 'in_stock', settings)
        assert sent1 == 1
        assert sent2 == 0
        assert len(bot.messages) == 1
        count = int((await session.execute(select(func.count(Notification.id)))).scalar_one())
        assert count == 1
