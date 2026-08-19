from __future__ import annotations

import logging
from typing import Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.config.settings import Settings

logger = logging.getLogger(__name__)


class ProductIntent(BaseModel):
    is_product: bool
    action: Literal['identify', 'track', 'find_cheaper', 'set_target', 'unknown'] = 'unknown'
    brand: str | None = None
    model: str | None = None
    variant: str | None = None
    normalized_name: str | None = None
    search_query: str | None = None
    target_price: float | None = None
    target_percent: float | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


SYSTEM_INSTRUCTIONS = '''
Ты — компактный модуль понимания товарных запросов Telegram-бота PRICE.
Твоя задача — только разобрать текст пользователя и нормализовать название товара.

Правила:
- Никогда не придумывай текущую цену, скидку, наличие, продавца или магазин.
- Не выполняй веб-поиск и не утверждай, что товар где-то продаётся.
- Если это не конкретный покупаемый товар или товарная модель, is_product=false.
- Исправляй очевидные разговорные формы и транслитерацию: например «айфон 16 про 256» -> «Apple iPhone 16 Pro 256 GB».
- brand — бренд, model — модель, variant — память/размер/цвет/версия, если они явно указаны.
- normalized_name — короткое человекочитаемое название без выдуманных характеристик.
- search_query — строка, подходящая для будущего поиска этого же товара.
- action=find_cheaper для «найди дешевле/где дешевле».
- action=track для «следи/отслеживай цену».
- action=set_target, если пользователь явно указал желаемую цену или процент снижения.
- action=identify для обычного названия товара.
- confidence отражает уверенность именно в разборе запроса, а не в существовании товара.
'''.strip()


class AIService:
    def __init__(self, settings: Settings, client: AsyncOpenAI | object | None = None):
        self.settings = settings
        self.enabled = bool(client is not None or settings.ai_available)
        self.client = client
        if self.client is None and self.enabled:
            self.client = AsyncOpenAI(
                api_key=settings.openai_api_key,
                timeout=settings.openai_timeout,
                max_retries=1,
            )

    async def analyze_product_text(self, text: str) -> ProductIntent | None:
        if not self.enabled or self.client is None:
            return None
        cleaned = text.strip()
        if not cleaned:
            return None
        try:
            response = await self.client.responses.parse(
                model=self.settings.openai_model,
                instructions=SYSTEM_INSTRUCTIONS,
                input=cleaned[:1000],
                text_format=ProductIntent,
                max_output_tokens=self.settings.openai_max_output_tokens,
                store=False,
            )
            parsed = response.output_parsed
            if isinstance(parsed, ProductIntent):
                return parsed
            return None
        except Exception as exc:
            # Never log the API key or the user's full prompt.
            logger.warning('OpenAI product analysis failed type=%s', exc.__class__.__name__)
            return None

    async def close(self) -> None:
        if self.client is not None and hasattr(self.client, 'close'):
            try:
                result = self.client.close()
                if result is not None:
                    await result
            except Exception:
                logger.debug('OpenAI client close failed', exc_info=True)
