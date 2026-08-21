from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database.models import User
from app.database.razberi_models import RazberiPayment, RazberiSubscription


def _to_naive_utc(value) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    if value:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).replace(tzinfo=None)
    return datetime.utcnow() + timedelta(days=30)


def _settings(user: User) -> dict:
    try:
        data = json.loads(user.notification_settings or '{}')
        return data if isinstance(data, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


class SubscriptionService:
    def __init__(self, db):
        self.db = db

    async def activate(
        self,
        user_id: int,
        charge_id: str,
        amount: int,
        expiration,
        is_recurring: bool,
        plan: str = 'PRO',
    ) -> datetime:
        expires_at = _to_naive_utc(expiration)
        plan = 'MAX' if str(plan).upper() == 'MAX' else 'PRO'
        async with self.db.sessions() as session:
            payment = (
                await session.execute(
                    select(RazberiPayment).where(RazberiPayment.telegram_charge_id == charge_id)
                )
            ).scalar_one_or_none()
            if payment is None:
                session.add(
                    RazberiPayment(
                        user_id=user_id,
                        telegram_charge_id=charge_id,
                        currency='XTR',
                        amount=amount,
                        status='paid',
                        is_recurring=is_recurring,
                    )
                )

            subscription = (
                await session.execute(
                    select(RazberiSubscription).where(
                        RazberiSubscription.telegram_charge_id == charge_id
                    )
                )
            ).scalar_one_or_none()
            if subscription is None:
                subscription = RazberiSubscription(
                    user_id=user_id,
                    telegram_charge_id=charge_id,
                    status='active',
                    is_recurring=is_recurring,
                    expires_at=expires_at,
                )
                session.add(subscription)
            else:
                subscription.status = 'active'
                subscription.expires_at = expires_at
                subscription.is_recurring = is_recurring

            user = await session.get(User, user_id)
            if user is not None:
                user.is_pro = True
                user.pro_until = expires_at
                data = _settings(user)
                data['clarify_plan'] = plan
                user.notification_settings = json.dumps(data, ensure_ascii=False)
            await session.commit()
        return expires_at

    async def add_request_pack(self, user_id: int, charge_id: str, amount: int, credits: int) -> int:
        credits = max(0, int(credits))
        async with self.db.sessions() as session:
            existing = (
                await session.execute(
                    select(RazberiPayment).where(RazberiPayment.telegram_charge_id == charge_id)
                )
            ).scalar_one_or_none()
            user = await session.get(User, user_id)
            if user is None:
                return 0
            data = _settings(user)
            if existing is None:
                session.add(
                    RazberiPayment(
                        user_id=user_id,
                        telegram_charge_id=charge_id,
                        currency='XTR',
                        amount=amount,
                        status='paid',
                        is_recurring=False,
                    )
                )
                data['clarify_bonus_requests'] = max(0, int(data.get('clarify_bonus_requests', 0) or 0)) + credits
                user.notification_settings = json.dumps(data, ensure_ascii=False)
                await session.commit()
            return max(0, int(data.get('clarify_bonus_requests', 0) or 0))

    async def remove_request_pack(self, user_id: int, credits: int) -> int:
        async with self.db.sessions() as session:
            user = await session.get(User, user_id)
            if user is None:
                return 0
            data = _settings(user)
            current = max(0, int(data.get('clarify_bonus_requests', 0) or 0))
            data['clarify_bonus_requests'] = max(0, current - max(0, int(credits)))
            user.notification_settings = json.dumps(data, ensure_ascii=False)
            await session.commit()
            return int(data['clarify_bonus_requests'])

    async def latest_active(self, user_id: int):
        async with self.db.sessions() as session:
            return (
                await session.execute(
                    select(RazberiSubscription)
                    .where(
                        RazberiSubscription.user_id == user_id,
                        RazberiSubscription.status == 'active',
                    )
                    .order_by(RazberiSubscription.created_at.desc())
                )
            ).scalars().first()

    async def mark_cancelled(self, user_id: int, charge_id: str):
        async with self.db.sessions() as session:
            subscription = (
                await session.execute(select(RazberiSubscription).where(
                    RazberiSubscription.user_id == user_id,
                    RazberiSubscription.telegram_charge_id == charge_id,
                ))
            ).scalar_one_or_none()
            if subscription is not None:
                subscription.status = 'cancelled'
            await session.commit()
            return subscription

    async def mark_refunded(self, charge_id: str):
        async with self.db.sessions() as session:
            payment = (
                await session.execute(
                    select(RazberiPayment).where(RazberiPayment.telegram_charge_id == charge_id)
                )
            ).scalar_one_or_none()
            if payment is None:
                return None
            payment.status = 'refunded'
            subscription = (
                await session.execute(
                    select(RazberiSubscription).where(
                        RazberiSubscription.telegram_charge_id == charge_id
                    )
                )
            ).scalar_one_or_none()
            if subscription is not None:
                subscription.status = 'refunded'
                user = await session.get(User, payment.user_id)
                if user is not None:
                    user.is_pro = False
                    user.pro_until = datetime.utcnow()
                    data = _settings(user)
                    data.pop('clarify_plan', None)
                    user.notification_settings = json.dumps(data, ensure_ascii=False)
            await session.commit()
            return payment
