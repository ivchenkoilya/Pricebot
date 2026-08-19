from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, requests_per_minute: int = 30, max_active_jobs: int = 2):
        self.rpm = max(1, requests_per_minute)
        self.max_active = max(1, max_active_jobs)
        self.hits = defaultdict(deque)
        self.active = defaultdict(int)
        self.lock = asyncio.Lock()

    async def __call__(self, handler, event, data):
        user = getattr(event, 'from_user', None)
        if user is None:
            return await handler(event, data)
        user_id = user.id
        now = time.monotonic()
        async with self.lock:
            queue = self.hits[user_id]
            while queue and now - queue[0] > 60:
                queue.popleft()
            if len(queue) >= self.rpm:
                if isinstance(event, Message):
                    await event.answer('⚠️ Слишком много запросов. Попробуй чуть позже.')
                elif isinstance(event, CallbackQuery):
                    await event.answer('Слишком много запросов', show_alert=True)
                return None
            if self.active[user_id] >= self.max_active:
                if isinstance(event, Message):
                    await event.answer('⏳ У тебя уже обрабатываются другие материалы. Дождись их завершения.')
                elif isinstance(event, CallbackQuery):
                    await event.answer('Уже есть активная обработка', show_alert=True)
                return None
            queue.append(now)
            self.active[user_id] += 1
        try:
            return await handler(event, data)
        finally:
            async with self.lock:
                self.active[user_id] = max(0, self.active[user_id] - 1)
