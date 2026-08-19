from datetime import datetime
from types import SimpleNamespace

import pytest

from app.database.models import User
from app.payments.stars import SUBSCRIPTION_PERIOD_SECONDS, activate_from_payment


@pytest.mark.asyncio
async def test_payment_activation_is_idempotent(db):
    database, _settings = db
    async with database.session_factory() as session:
        user = User(telegram_id=777)
        session.add(user)
        await session.commit()
        payment = SimpleNamespace(
            telegram_payment_charge_id='charge_1',
            total_amount=199,
            subscription_expiration_date=int(datetime.utcnow().timestamp()) + SUBSCRIPTION_PERIOD_SECONDS,
        )
        msg = SimpleNamespace(successful_payment=payment)
        sub1 = await activate_from_payment(session, user, msg)
        sub2 = await activate_from_payment(session, user, msg)
        assert sub1.id == sub2.id
        assert user.is_pro is True
        assert sub1.stars_amount == 199
