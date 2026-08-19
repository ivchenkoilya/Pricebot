from __future__ import annotations

from urllib.parse import urlsplit

from app.config.settings import Settings
from app.services.ai import AIService
from app.services.page_reader import PageReadError, PageReader
from app.trackers.base import PriceProvider, ProductSnapshot, ProviderError
from app.utils.url import normalize_url


class AIPageProvider(PriceProvider):
    """Last-resort product identity provider for public pages.

    This provider deliberately never sets current_price. It can understand what
    product a page is about after the deterministic price parsers fail, but a
    price only becomes authoritative when a dedicated/provider parser confirms it.
    """

    name = 'page-ai'

    def __init__(self, settings: Settings):
        self.settings = settings
        self.reader = PageReader(settings)
        self.ai = AIService(settings)

    async def supports(self, url: str) -> bool:
        if not self.ai.enabled:
            return False
        try:
            parts = urlsplit(normalize_url(url))
            return parts.scheme in {'http', 'https'} and bool(parts.hostname)
        except ValueError:
            return False

    async def fetch(self, url: str) -> ProductSnapshot:
        try:
            page = await self.reader.read(url)
        except PageReadError as exc:
            raise ProviderError(f'page reader: {exc}') from exc

        insight = await self.ai.analyze_page(page.final_url, page.title, page.text)
        if insight is None:
            raise ProviderError('AI не смог разобрать содержимое страницы')
        if not insight.is_product or insight.confidence < 0.45:
            raise ProviderError('Страница не распознана как карточка конкретного товара')

        host = urlsplit(page.final_url).hostname or urlsplit(url).hostname or 'unknown'
        name = (
            insight.product_name
            or ' '.join(part for part in (insight.brand, insight.model, insight.variant) if part)
            or page.title
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
            source=host,
            confidence=min(float(insight.confidence), 0.84),
        )
