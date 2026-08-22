from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select

from app.database.models import User
from app.database.razberi_models import AIUsage, Metric, Referral, UserAcquisition


_PAYLOAD_RE = re.compile(r'[^a-zA-Z0-9_-]+')
_REF_RE = re.compile(r'^ref_(\d+)$', re.I)


@dataclass(frozen=True, slots=True)
class ParsedStart:
    source: str
    campaign: str | None
    raw_payload: str
    referrer_telegram_id: int | None = None


@dataclass(frozen=True, slots=True)
class ReferralReward:
    referrer_telegram_id: int
    referred_telegram_id: int
    amount: int


@dataclass(frozen=True, slots=True)
class ReferralStats:
    invited_total: int
    rewarded_total: int
    earned_requests: int
    source: str
    campaign: str | None


def parse_start_payload(payload: str | None) -> ParsedStart:
    raw = (payload or '').strip()[:255]
    if not raw:
        return ParsedStart(source='direct', campaign=None, raw_payload='')

    safe = _PAYLOAD_RE.sub('_', raw).strip('_').lower()[:128]
    match = _REF_RE.fullmatch(safe)
    if match:
        return ParsedStart(
            source='referral',
            campaign=None,
            raw_payload=safe,
            referrer_telegram_id=int(match.group(1)),
        )

    if safe.startswith('tiktok'):
        source = 'tiktok'
    elif safe.startswith('youtube') or safe.startswith('shorts'):
        source = 'youtube'
    elif safe.startswith('ads_') or safe.startswith('telegram_ads'):
        source = 'telegram_ads'
    elif safe.startswith('tg_') or safe.startswith('telegram'):
        source = 'telegram'
    else:
        source = safe.split('_', 1)[0] or 'campaign'

    return ParsedStart(source=source[:64], campaign=safe[:128], raw_payload=safe)


def build_referral_link(bot_username: str, telegram_id: int) -> str:
    username = (bot_username or '').strip().lstrip('@')
    return f'https://t.me/{username}?start=ref_{int(telegram_id)}'


def _settings_dict(user: User) -> dict:
    try:
        value = json.loads(user.notification_settings or '{}')
        return value if isinstance(value, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _add_bonus(user: User, amount: int) -> None:
    data = _settings_dict(user)
    current = max(0, int(data.get('clarify_bonus_requests', 0) or 0))
    data['clarify_bonus_requests'] = current + max(0, int(amount))
    user.notification_settings = json.dumps(data, ensure_ascii=False)


class GrowthService:
    """First-touch attribution, referral anti-abuse and growth funnel metrics."""

    def __init__(self, db, settings):
        self.db = db
        self.settings = settings

    async def capture_start(self, user_id: int, payload: str | None) -> ParsedStart:
        parsed = parse_start_payload(payload)
        async with self.db.sessions() as session:
            existing = (
                await session.execute(
                    select(UserAcquisition).where(UserAcquisition.user_id == user_id)
                )
            ).scalar_one_or_none()
            if existing is not None:
                # First-touch attribution is immutable. Reopening the bot through
                # another campaign or somebody else's referral never overwrites it.
                return ParsedStart(
                    source=existing.source,
                    campaign=existing.campaign,
                    raw_payload=existing.raw_payload,
                )

            acquisition = UserAcquisition(
                user_id=user_id,
                source=parsed.source,
                campaign=parsed.campaign,
                raw_payload=parsed.raw_payload,
            )
            session.add(acquisition)
            session.add(Metric(name='registration', user_id=user_id, value=1))
            session.add(Metric(name=f'source_{parsed.source}'[:64], user_id=user_id, value=1))

            if parsed.referrer_telegram_id is not None:
                referrer = (
                    await session.execute(
                        select(User).where(User.telegram_id == parsed.referrer_telegram_id)
                    )
                ).scalar_one_or_none()
                if referrer is not None and referrer.id != user_id:
                    existing_ref = (
                        await session.execute(
                            select(Referral).where(Referral.referred_user_id == user_id)
                        )
                    ).scalar_one_or_none()
                    if existing_ref is None:
                        session.add(
                            Referral(
                                referrer_user_id=referrer.id,
                                referred_user_id=user_id,
                                status='pending',
                            )
                        )
                        session.add(Metric(name='referral_opened', user_id=user_id, value=1))

            await session.commit()
        return parsed

    async def sync_conversion(self, telegram_id: int) -> ReferralReward | None:
        """Mark first successful AI use and grant a pending referral exactly once."""
        async with self.db.sessions() as session:
            user = (
                await session.execute(select(User).where(User.telegram_id == int(telegram_id)))
            ).scalar_one_or_none()
            if user is None:
                return None

            has_ai_usage = (
                await session.execute(
                    select(AIUsage.id).where(AIUsage.user_id == user.id).limit(1)
                )
            ).scalar_one_or_none()
            if has_ai_usage is None:
                return None

            acquisition = (
                await session.execute(
                    select(UserAcquisition).where(UserAcquisition.user_id == user.id)
                )
            ).scalar_one_or_none()
            if acquisition is None:
                acquisition = UserAcquisition(user_id=user.id, source='direct', raw_payload='')
                session.add(acquisition)

            if acquisition.first_analysis_at is None:
                acquisition.first_analysis_at = datetime.utcnow()
                session.add(Metric(name='first_successful_analysis', user_id=user.id, value=1))

            referral = (
                await session.execute(
                    select(Referral).where(
                        Referral.referred_user_id == user.id,
                        Referral.status == 'pending',
                    )
                )
            ).scalar_one_or_none()
            if referral is None:
                await session.commit()
                return None

            # Existing Clarify users must not be able to open a referral link
            # after they already used AI and instantly trigger a reward. The
            # qualifying AI operation has to happen after this referral record.
            qualifying_ai_usage = (
                await session.execute(
                    select(AIUsage.id).where(
                        AIUsage.user_id == user.id,
                        AIUsage.created_at >= referral.created_at,
                    ).limit(1)
                )
            ).scalar_one_or_none()
            if qualifying_ai_usage is None:
                await session.commit()
                return None

            referrer = await session.get(User, referral.referrer_user_id)
            referred = await session.get(User, referral.referred_user_id)
            if referrer is None or referred is None or referrer.id == referred.id:
                referral.status = 'invalid'
                await session.commit()
                return None

            amount = max(1, int(self.settings.referral_bonus_requests))
            _add_bonus(referrer, amount)
            _add_bonus(referred, amount)
            referral.status = 'rewarded'
            referral.reward_amount = amount
            referral.rewarded_at = datetime.utcnow()
            session.add(Metric(name='referral_conversion', user_id=referred.id, value=1))
            session.add(Metric(name='referral_reward', user_id=referrer.id, value=amount))
            session.add(Metric(name='referral_reward', user_id=referred.id, value=amount))
            await session.commit()

            return ReferralReward(
                referrer_telegram_id=int(referrer.telegram_id),
                referred_telegram_id=int(referred.telegram_id),
                amount=amount,
            )

    async def stats(self, user_id: int) -> ReferralStats:
        async with self.db.sessions() as session:
            invited = int(
                (
                    await session.execute(
                        select(func.count(Referral.id)).where(Referral.referrer_user_id == user_id)
                    )
                ).scalar_one()
            )
            rewarded = int(
                (
                    await session.execute(
                        select(func.count(Referral.id)).where(
                            Referral.referrer_user_id == user_id,
                            Referral.status == 'rewarded',
                        )
                    )
                ).scalar_one()
            )
            earned = int(
                (
                    await session.execute(
                        select(func.coalesce(func.sum(Referral.reward_amount), 0)).where(
                            Referral.referrer_user_id == user_id,
                            Referral.status == 'rewarded',
                        )
                    )
                ).scalar_one()
            )
            acquisition = (
                await session.execute(
                    select(UserAcquisition).where(UserAcquisition.user_id == user_id)
                )
            ).scalar_one_or_none()

        return ReferralStats(
            invited_total=invited,
            rewarded_total=rewarded,
            earned_requests=earned,
            source=acquisition.source if acquisition else 'direct',
            campaign=acquisition.campaign if acquisition else None,
        )

    async def dashboard(self) -> dict[str, object]:
        async with self.db.sessions() as session:
            registrations = int((await session.execute(select(func.count(UserAcquisition.id)))).scalar_one())
            first_analyses = int(
                (
                    await session.execute(
                        select(func.count(UserAcquisition.id)).where(UserAcquisition.first_analysis_at.is_not(None))
                    )
                ).scalar_one()
            )
            referral_opened = int((await session.execute(select(func.count(Referral.id)))).scalar_one())
            referral_converted = int(
                (
                    await session.execute(
                        select(func.count(Referral.id)).where(Referral.status == 'rewarded')
                    )
                ).scalar_one()
            )
            source_rows = list(
                (
                    await session.execute(
                        select(UserAcquisition.source, func.count(UserAcquisition.id))
                        .group_by(UserAcquisition.source)
                        .order_by(func.count(UserAcquisition.id).desc())
                    )
                ).all()
            )

        return {
            'registrations': registrations,
            'first_analyses': first_analyses,
            'referral_opened': referral_opened,
            'referral_converted': referral_converted,
            'sources': [(str(source), int(count)) for source, count in source_rows],
        }
