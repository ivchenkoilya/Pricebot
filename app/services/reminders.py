from __future__ import annotations

from datetime import datetime, timezone

from dateparser.search import search_dates
from sqlalchemy import select

from app.database.models import User
from app.database.razberi_models import Reminder


def parse_reminder(text: str, timezone_name: str):
    cleaned = (text or '').strip()
    lowered = cleaned.lower()
    for prefix in ('напомни мне ', 'напомни '):
        if lowered.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    found = search_dates(
        cleaned,
        languages=['ru'],
        settings={
            'TIMEZONE': timezone_name,
            'RETURN_AS_TIMEZONE_AWARE': True,
            'PREFER_DATES_FROM': 'future',
        },
    )
    if not found:
        return None
    phrase, value = found[0]
    task = cleaned.replace(phrase, ' ', 1).strip(' ,.-') or 'Напоминание'
    utc_value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return task, utc_value


class ReminderService:
    def __init__(self, db):
        self.db = db

    async def create_pending(self, user_id: int, text: str, remind_at: datetime):
        async with self.db.sessions() as session:
            reminder = Reminder(user_id=user_id, text=text, remind_at=remind_at, status='pending')
            session.add(reminder)
            await session.commit()
            await session.refresh(reminder)
            return reminder

    async def activate(self, user_id: int, reminder_id: int):
        async with self.db.sessions() as session:
            reminder = (
                await session.execute(
                    select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == user_id)
                )
            ).scalar_one_or_none()
            if reminder is None:
                return None
            reminder.status = 'active'
            await session.commit()
            return reminder

    async def cancel(self, user_id: int, reminder_id: int):
        async with self.db.sessions() as session:
            reminder = (
                await session.execute(
                    select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == user_id)
                )
            ).scalar_one_or_none()
            if reminder is not None:
                reminder.status = 'cancelled'
                await session.commit()
            return reminder

    async def due(self):
        now = datetime.utcnow()
        async with self.db.sessions() as session:
            rows = list(
                (
                    await session.execute(
                        select(Reminder, User.telegram_id)
                        .join(User, User.id == Reminder.user_id)
                        .where(Reminder.status == 'active', Reminder.remind_at <= now)
                    )
                ).all()
            )
            for reminder, _telegram_id in rows:
                reminder.status = 'sent'
                reminder.sent_at = now
            await session.commit()
            return rows
