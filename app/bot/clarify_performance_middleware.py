from __future__ import annotations

import logging
import time

from aiogram import BaseMiddleware


log = logging.getLogger('clarify.performance')


class PerformanceMiddleware(BaseMiddleware):
    """Measure end-to-end Telegram handler latency without touching responses."""

    def __init__(self, ctx, slow_seconds: float = 5.0):
        self.ctx = ctx
        self.slow_seconds = max(0.5, float(slow_seconds))

    async def __call__(self, handler, event, data):
        started = time.perf_counter()
        telegram_user = getattr(event, 'from_user', None)
        event_name = event.__class__.__name__
        failed = False
        try:
            return await handler(event, data)
        except Exception:
            failed = True
            raise
        finally:
            elapsed = time.perf_counter() - started
            user_id = int(getattr(telegram_user, 'id', 0) or 0) or None
            log.info(
                'request_done event=%s user=%s latency_ms=%d failed=%s',
                event_name,
                user_id or '-',
                int(elapsed * 1000),
                failed,
            )
            if elapsed >= self.slow_seconds:
                try:
                    await self.ctx.metrics.inc('slow_request', None, 1)
                except Exception:
                    log.exception('Could not record slow request metric')
