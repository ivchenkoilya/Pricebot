from __future__ import annotations

import re
from urllib.parse import urlsplit

from app.config.settings import Settings
from app.services.ai import AIService
from app.services.page_reader import PageReadError, PageReader
from app.trackers.base import PriceProvider, ProductSnapshot, ProviderError
from app.utils.url import normalize_url


class AIPageProvider(PriceProvider):
    """Last-resort public-page identity provider.

    It first reads the page. AI improves product extraction when available, but
    page reading itself is useful even if the AI gateway/model is temporarily
    broken. This provider deliberately never sets current_price: monitored prices
    remain authoritative only when a deterministic store/parser confirms them.
    """

    name = 'page-ai'

    def __init__(self, settings: Settings):
        self.settings = settings
        self.reader = PageReader(settings)
        self.ai = AIService(settings)

    async def supports(self, url: str) -> bool:
        try:
            parts = urlsplit(normalize_url(url))
            return parts.scheme in {'http', 'https'} and bool(parts.hostname)
        except ValueError:
            return False

    @staticmethod
    def _fallback_title(page) -> str | None:
        title = re.sub(r'\s+', ' ', (page.title or '')).strip()
        if len(title) < 4:
            return None
        low = title.lower()
        generic = (
            'ozon маркетплейс', 'ozon — интернет-магазин', 'ozon - интернет-магазин',
            'доступ ограничен', 'access denied', 'captcha', 'just a moment',
        )
        if any(marker in low for marker in generic):
            return None
        return title[:500]

    async def fetch(self, url: str) -> ProductSnapshot:
        try:
            page = await self.reader.read(url)
        except PageReadError as exc:
            raise ProviderError(f'page reader: {exc}') from exc

        host = urlsplit(page.final_url).hostname or urlsplit(url).hostname or 'unknown'
        insight = await self.ai.analyze_page(page.final_url, page.title, page.text) if self.ai.enabled else None

        if insight is not None and insight.is_product and insight.confidence >= 0.45:
            name = (
                insight.product_name
                or ' '.join(part for part in (insight.brand, insight.model, insight.variant) if part)
                or self._fallback_title(page)
                or host
            )
            name = str(name).strip()[:500]

            availability = 'unknown'
            availability_text = (insight.availability_text or '').lower()
            if any(marker in availability_text for marker in ('в наличии', 'доступен', 'в корзину', 'купить', 'in stock')):
                availability = 'in_stock'
            elif any(marker in availability_text for marker in ('нет в наличии', 'законч', 'распродан', 'out of stock', 'sold out')):
                availability = 'out_of_stock'

            return ProductSnapshot(
                product_name=name,
                current_price=None,
                old_price=None,
                currency=None,
                availability=availability,
                image_url=None,
                canonical_url=normalize_url(page.final_url),
                seller=(insight.seller or None),
                source=f'{host} via {page.source}',
                confidence=min(float(insight.confidence), 0.84),
            )

        # AI can fail because a third-party gateway has the wrong model ID/base
        # URL. Do not throw away a page we already managed to read. A meaningful
        # page title still lets PRICE identify what is behind the link while the
        # price remains explicitly unconfirmed.
        fallback_name = self._fallback_title(page)
        if fallback_name:
            return ProductSnapshot(
                product_name=fallback_name,
                current_price=None,
                old_price=None,
                currency=None,
                availability='unknown',
                image_url=None,
                canonical_url=normalize_url(page.final_url),
                seller=None,
                source=f'{host} via {page.source}',
                confidence=0.46,
            )

        if insight is None and self.ai.enabled:
            raise ProviderError(f'Reader={page.source}: страница прочитана, но AI gateway/model не разобрал содержимое')
        if insight is None:
            raise ProviderError(f'Reader={page.source}: страница прочитана, но AI отключён и title недостаточно информативен')
        raise ProviderError(f'Reader={page.source}: страница прочитана, но не распознана как карточка товара')
