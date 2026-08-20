from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta

from sqlalchemy import select

from app.database.razberi_models import ConversationState


class ConversationContextService:
    """Small per-user working context around persistent materials.

    Materials stay in normal history. /clear only advances a persistent cutoff so
    old materials are no longer used as implicit follow-up context. A tiny
    in-memory turn buffer improves follow-up wording without duplicating full
    documents in the database.
    """

    def __init__(self, db, materials, settings):
        self.db = db
        self.materials = materials
        self.settings = settings
        self._history: dict[int, deque[tuple[str, str]]] = defaultdict(lambda: deque(maxlen=10))

    async def cutoff(self, user_id: int) -> datetime | None:
        async with self.db.sessions() as session:
            state = (
                await session.execute(select(ConversationState).where(ConversationState.user_id == user_id))
            ).scalar_one_or_none()
            return state.cleared_at if state else None

    async def clear(self, user_id: int) -> None:
        now = datetime.utcnow()
        async with self.db.sessions() as session:
            state = (
                await session.execute(select(ConversationState).where(ConversationState.user_id == user_id))
            ).scalar_one_or_none()
            if state is None:
                state = ConversationState(user_id=user_id, cleared_at=now, updated_at=now)
                session.add(state)
            else:
                state.cleared_at = now
                state.updated_at = now
            await session.commit()
        self._history.pop(user_id, None)

    async def recent_materials(self, user_id: int, limit: int = 10):
        # Fetch a little extra because a clear cutoff can hide older rows.
        items = await self.materials.latest(user_id, max(limit * 3, 12))
        if not items:
            return []

        cutoff = await self.cutoff(user_id)
        recent_after = datetime.utcnow() - timedelta(hours=self.settings.recent_material_hours)
        effective_cutoff = max(filter(None, (cutoff, recent_after)))
        active = [
            item for item in items
            if getattr(item, 'created_at', None) and item.created_at >= effective_cutoff
        ]
        return active[:limit]

    def remember(self, user_id: int, role: str, text: str) -> None:
        clean = ' '.join((text or '').split())[:1200]
        if clean:
            self._history[user_id].append((role[:16], clean))

    def history_text(self, user_id: int, limit: int = 8) -> str:
        rows = list(self._history.get(user_id, ()))
        if not rows:
            return ''
        labels = {'user': 'Пользователь', 'assistant': 'Clarify'}
        return '\n'.join(f'{labels.get(role, role)}: {text}' for role, text in rows[-limit:])
