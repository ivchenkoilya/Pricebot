from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.utils.rate_limit import SlidingWindowRateLimiter


class UserRateLimitMiddleware(BaseMiddleware):
    def __init__(self, limit_per_minute: int):
        self.limiter = SlidingWindowRateLimiter(limit_per_minute, 60)

    async def __call__(self, handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: Dict[str, Any]) -> Any:
        user = data.get('event_from_user')
        if user and not self.limiter.allow(int(user.id)):
            if hasattr(event, 'answer'):
                try:
                    await event.answer('Слишком много запросов. Попробуй через минуту.')
                except Exception:
                    pass
            return None
        return await handler(event, data)
