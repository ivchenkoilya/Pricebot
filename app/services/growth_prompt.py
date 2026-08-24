from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.database.models import User
from app.database.razberi_models import AIUsage, Metric
from app.services.growth import GrowthService, _settings_dict


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


class GrowthPromptService(GrowthService):
    """Growth service with a deliberately non-spammy referral CTA scheduler."""

    async def successful_count(self, telegram_id: int) -> int:
        async with self.db.sessions() as session:
            user = (
                await session.execute(select(User).where(User.telegram_id == int(telegram_id)))
            ).scalar_one_or_none()
            if user is None:
                return 0
            return int(
                (
                    await session.execute(
                        select(func.count(AIUsage.id)).where(AIUsage.user_id == user.id)
                    )
                ).scalar_one()
            )

    async def referral_prompt_due(self, telegram_id: int) -> bool:
        """Reserve a referral CTA slot if the user has earned one.

        The reservation and timestamp are committed before sending, so another
        Telegram update cannot create a duplicate prompt at the same threshold.
        """
        now = datetime.utcnow()
        async with self.db.sessions() as session:
            user = (
                await session.execute(select(User).where(User.telegram_id == int(telegram_id)))
            ).scalar_one_or_none()
            if user is None:
                return False

            successes = int(
                (
                    await session.execute(
                        select(func.count(AIUsage.id)).where(AIUsage.user_id == user.id)
                    )
                ).scalar_one()
            )
            first = max(1, int(self.settings.referral_prompt_first_success))
            every = max(1, int(self.settings.referral_prompt_every_successes))
            if successes < first:
                return False

            data = _settings_dict(user)
            last_count = max(0, int(data.get('clarify_referral_prompt_success_count', 0) or 0))
            if last_count == 0:
                count_due = successes >= first
            else:
                count_due = successes - last_count >= every
            if not count_due:
                return False

            dismiss_count = max(0, int(data.get('clarify_referral_prompt_dismiss_count', 0) or 0))
            # A person who repeatedly says "not now" sees the CTA progressively
            # less often: 3d -> 6d -> 9d -> 12d (capped). This is deliberately
            # independent from the success counter so it cannot become spammy.
            cooldown_multiplier = min(4, 1 + dismiss_count)
            last_shown = _parse_dt(data.get('clarify_referral_prompt_shown_at'))
            cooldown = timedelta(
                days=max(0, int(self.settings.referral_prompt_cooldown_days)) * cooldown_multiplier
            )
            if last_shown and now - last_shown < cooldown:
                return False

            last_clicked = _parse_dt(data.get('clarify_referral_prompt_clicked_at'))
            click_cooldown = timedelta(days=max(0, int(self.settings.referral_prompt_after_click_days)))
            if last_clicked and now - last_clicked < click_cooldown:
                return False

            data['clarify_referral_prompt_success_count'] = successes
            data['clarify_referral_prompt_shown_at'] = now.isoformat()
            user.notification_settings = json.dumps(data, ensure_ascii=False)
            session.add(Metric(name='referral_prompt_shown', user_id=user.id, value=1))
            await session.commit()
            return True

    async def mark_referral_prompt_clicked(self, user_id: int) -> None:
        async with self.db.sessions() as session:
            user = await session.get(User, int(user_id))
            if user is None:
                return
            data = _settings_dict(user)
            data['clarify_referral_prompt_clicked_at'] = datetime.utcnow().isoformat()
            # Clicking means the CTA was useful; reset accumulated dismissals.
            data['clarify_referral_prompt_dismiss_count'] = 0
            user.notification_settings = json.dumps(data, ensure_ascii=False)
            session.add(Metric(name='referral_prompt_clicked', user_id=user.id, value=1))
            await session.commit()

    async def mark_referral_prompt_dismissed(self, user_id: int) -> int:
        async with self.db.sessions() as session:
            user = await session.get(User, int(user_id))
            if user is None:
                return 0
            data = _settings_dict(user)
            count = max(0, int(data.get('clarify_referral_prompt_dismiss_count', 0) or 0)) + 1
            data['clarify_referral_prompt_dismiss_count'] = min(count, 20)
            data['clarify_referral_prompt_dismissed_at'] = datetime.utcnow().isoformat()
            user.notification_settings = json.dumps(data, ensure_ascii=False)
            session.add(Metric(name='referral_prompt_dismissed', user_id=user.id, value=1))
            await session.commit()
            return count
