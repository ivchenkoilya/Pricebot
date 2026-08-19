from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

from openai import (
    APIConnectionError,
    APIStatusError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    RateLimitError,
)
from pydantic import BaseModel, Field, ValidationError

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


@dataclass(slots=True)
class AIProbeResult:
    ok: bool
    code: str
    message: str


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

JSON_INSTRUCTIONS = SYSTEM_INSTRUCTIONS + '''

Верни ТОЛЬКО один JSON-объект без markdown со следующими полями:
{"is_product": true/false, "action": "identify|track|find_cheaper|set_target|unknown", "brand": null|string, "model": null|string, "variant": null|string, "normalized_name": null|string, "search_query": null|string, "target_price": null|number, "target_percent": null|number, "confidence": number от 0 до 1}.
'''


def _extract_json_object(text: str) -> dict | None:
    value = text.strip()
    if value.startswith('```'):
        value = re.sub(r'^```(?:json)?\s*', '', value, flags=re.I)
        value = re.sub(r'\s*```$', '', value)
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', value, flags=re.S)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None


class AIService:
    def __init__(self, settings: Settings, client: AsyncOpenAI | object | None = None):
        self.settings = settings
        self.enabled = bool(client is not None or settings.ai_available)
        self.client = client
        if self.client is None and self.enabled:
            kwargs = {
                'api_key': settings.openai_api_key,
                'timeout': settings.openai_timeout,
                'max_retries': 1,
            }
            if settings.openai_base_url.strip():
                kwargs['base_url'] = settings.openai_base_url.strip().rstrip('/')
            self.client = AsyncOpenAI(**kwargs)

    @property
    def endpoint_label(self) -> str:
        if not self.settings.openai_base_url.strip():
            return 'api.openai.com'
        try:
            parsed = urlparse(self.settings.openai_base_url.strip())
            return parsed.netloc or 'custom'
        except Exception:
            return 'custom'

    async def analyze_product_text(self, text: str) -> ProductIntent | None:
        if not self.enabled or self.client is None:
            return None
        cleaned = text.strip()
        if not cleaned:
            return None
        try:
            if self.settings.ai_uses_custom_endpoint:
                return await self._analyze_openai_compatible(cleaned)
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
            logger.warning('AI product analysis failed endpoint=%s type=%s', self.endpoint_label, exc.__class__.__name__)
            return None

    async def _analyze_openai_compatible(self, cleaned: str) -> ProductIntent | None:
        response = await self.client.chat.completions.create(
            model=self.settings.openai_model,
            messages=[
                {'role': 'system', 'content': JSON_INSTRUCTIONS},
                {'role': 'user', 'content': cleaned[:1000]},
            ],
            temperature=0,
        )
        content = response.choices[0].message.content or ''
        payload = _extract_json_object(content)
        if payload is None:
            return None
        try:
            return ProductIntent.model_validate(payload)
        except ValidationError:
            return None

    async def probe(self) -> AIProbeResult:
        if not self.enabled or self.client is None:
            return AIProbeResult(False, 'disabled', 'OPENAI_API_KEY не задан или AI отключён.')
        try:
            if self.settings.ai_uses_custom_endpoint:
                response = await self.client.chat.completions.create(
                    model=self.settings.openai_model,
                    messages=[{'role': 'user', 'content': 'Ответь только OK'}],
                    temperature=0,
                )
                if not response.choices:
                    return AIProbeResult(False, 'empty', 'API ответил, но не вернул результат.')
            else:
                response = await self.client.responses.create(
                    model=self.settings.openai_model,
                    input='Reply only OK',
                    max_output_tokens=8,
                    store=False,
                )
                if not getattr(response, 'output', None):
                    return AIProbeResult(False, 'empty', 'API ответил, но не вернул результат.')
            return AIProbeResult(True, 'ok', 'Соединение с AI API работает.')
        except AuthenticationError:
            return AIProbeResult(False, 'auth', 'Ключ отклонён API. Проверь ключ и Base URL.')
        except RateLimitError:
            return AIProbeResult(False, 'rate_limit', 'API отклонил запрос из-за лимита/баланса или rate limit.')
        except NotFoundError:
            return AIProbeResult(False, 'not_found', 'Endpoint или выбранная модель не найдены.')
        except BadRequestError as exc:
            message = str(exc).lower()
            if 'model' in message:
                return AIProbeResult(False, 'model', 'API не принимает выбранную модель. Укажи Model ID из SmartAPI.')
            return AIProbeResult(False, 'bad_request', 'API отклонил формат запроса. Проверь модель и совместимость endpoint.')
        except APIConnectionError:
            return AIProbeResult(False, 'connection', 'Не удалось соединиться с API. Проверь OPENAI_BASE_URL.')
        except APIStatusError as exc:
            return AIProbeResult(False, f'http_{exc.status_code}', f'API вернул HTTP {exc.status_code}.')
        except Exception as exc:
            logger.warning('AI probe failed endpoint=%s type=%s', self.endpoint_label, exc.__class__.__name__)
            return AIProbeResult(False, 'unknown', f'Ошибка соединения: {exc.__class__.__name__}.')

    async def close(self) -> None:
        if self.client is not None and hasattr(self.client, 'close'):
            try:
                result = self.client.close()
                if result is not None:
                    await result
            except Exception:
                logger.debug('OpenAI client close failed', exc_info=True)
