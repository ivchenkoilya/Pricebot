from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import func, select

from app.database.models import User
from app.database.razberi_models import AIUsage
from app.services.core import (
    UsageService,
    bonus_requests,
    clarify_plan,
    is_creator,
    plan_daily_ai_limit,
    user_settings_dict,
)


def plan_monthly_ai_limit(user: User, settings) -> int | None:
    """Hidden fair-use ceiling for paid plans.

    FREE remains governed by its daily allowance. OWNER is unlimited. Purchased
    bonus requests may continue beyond this guard because those requests were
    paid for separately.
    """
    plan = clarify_plan(user, settings)
    if plan == 'PRO':
        return max(1, int(settings.pro_monthly_ai_limit))
    if plan == 'MAX':
        return max(1, int(settings.max_monthly_ai_limit))
    return None


class GuardedUsageService(UsageService):
    """UsageService with a subscription fair-use guard and durable bonus spend."""

    @staticmethod
    def _month_start() -> datetime:
        now = datetime.utcnow()
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    async def ai_count_month(self, user_id: int) -> int:
        async with self.db.sessions() as session:
            return int(
                (
                    await session.execute(
                        select(func.count(AIUsage.id)).where(
                            AIUsage.user_id == user_id,
                            AIUsage.created_at >= self._month_start(),
                        )
                    )
                ).scalar_one()
            )

    async def allowed(self, user: User, feature: str = 'ai') -> bool:
        del feature
        if is_creator(user, self.settings):
            return True

        daily_limit = plan_daily_ai_limit(user, self.settings)
        monthly_limit = plan_monthly_ai_limit(user, self.settings)
        today = await self.ai_count_today(user.id)
        month = await self.ai_count_month(user.id) if monthly_limit is not None else 0

        daily_ok = daily_limit is None or today < daily_limit
        monthly_ok = monthly_limit is None or month < monthly_limit
        if daily_ok and monthly_ok:
            return True

        # One-time packs/referral bonuses are a separately acquired balance and
        # therefore may extend a plan beyond its ordinary daily/monthly allowance.
        return bonus_requests(user) > 0

    async def record(self, user_id: int, model: str, feature: str, usage: dict | None = None):
        usage = usage or {}
        async with self.db.sessions() as session:
            user = await session.get(User, user_id)
            if user is not None and not is_creator(user, self.settings):
                daily_count = int(
                    (
                        await session.execute(
                            select(func.count(AIUsage.id)).where(
                                AIUsage.user_id == user_id,
                                AIUsage.created_at >= self._today_start(),
                            )
                        )
                    ).scalar_one()
                )
                monthly_limit = plan_monthly_ai_limit(user, self.settings)
                monthly_count = 0
                if monthly_limit is not None:
                    monthly_count = int(
                        (
                            await session.execute(
                                select(func.count(AIUsage.id)).where(
                                    AIUsage.user_id == user_id,
                                    AIUsage.created_at >= self._month_start(),
                                )
                            )
                        ).scalar_one()
                    )

                daily_limit = plan_daily_ai_limit(user, self.settings)
                over_daily = daily_limit is not None and daily_count >= daily_limit
                over_monthly = monthly_limit is not None and monthly_count >= monthly_limit
                if over_daily or over_monthly:
                    data = user_settings_dict(user)
                    extra = max(0, int(data.get('clarify_bonus_requests', 0) or 0))
                    if extra > 0:
                        data['clarify_bonus_requests'] = extra - 1
                        user.notification_settings = json.dumps(data, ensure_ascii=False)

            session.add(
                AIUsage(
                    user_id=user_id,
                    model=(model or '')[:255],
                    feature=feature[:64],
                    input_tokens=int(usage.get('input', 0) or 0),
                    output_tokens=int(usage.get('output', 0) or 0),
                    estimated_cost=0.0,
                )
            )
            await session.commit()
