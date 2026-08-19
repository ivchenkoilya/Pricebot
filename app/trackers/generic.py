from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

from app.config.settings import Settings
from app.trackers.base import PriceNotFoundError, PriceProvider, ProductSnapshot, ProviderError, SourceBlockedError
from app.utils.money import parse_price
from app.utils.url import ensure_safe_url, normalize_url, redirect_url

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Candidate:
    price: Decimal
    currency: str | None
    confidence: float
    source: str


class FetchLimiter:
    def __init__(self, global_limit: int, per_host_limit: int, min_host_interval: float):
        self.global_sem = asyncio.Semaphore(global_limit)
        self.per_host_limit = per_host_limit
        self.min_host_interval = min_host_interval
        self.host_sems: dict[str, asyncio.Semaphore] = {}
        self.host_locks: dict[str, asyncio.Lock] = {}
        self.last_host_request: dict[str, float] = {}

    def host(self, hostname: str) -> asyncio.Semaphore:
        return self.host_sems.setdefault(hostname, asyncio.Semaphore(self.per_host_limit))

    async def wait_host(self, hostname: str) -> None:
        loop = asyncio.get_running_loop()
        lock = self.host_locks.setdefault(hostname, asyncio.Lock())
        async with lock:
            last = self.last_host_request.get(hostname, 0.0)
            delay = self.min_host_interval - (loop.time() - last)
            if delay > 0:
                await asyncio.sleep(delay)
            self.last_host_request[hostname] = loop.time()


class GenericProvider(PriceProvider):
    name = 'generic'

    def __init__(self, settings: Settings):
        self.settings = settings
        self.limiter = FetchLimiter(settings.global_fetch_concurrency, settings.per_host_fetch_concurrency, settings.min_host_request_interval_seconds)

    async def supports(self, url: str) -> bool:
        try:
            parts = urlsplit(normalize_url(url))
            return parts.scheme in {'http', 'https'} and bool(parts.hostname)
        except ValueError:
            return False

    async def _get_html(self, url: str) -> tuple[str, str, str]:
        current = await ensure_safe_url(url)
        headers = {
            'User-Agent': self.settings.provider_user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.5',
            'Accept-Language': 'ru,en;q=0.8',
        }
        timeout = httpx.Timeout(self.settings.request_timeout)
        async with self.limiter.global_sem:
            for _ in range(6):
                host = urlsplit(current).hostname or ''
                async with self.limiter.host(host):
                    await self.limiter.wait_host(host)
                    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, headers=headers) as client:
                        try:
                            response = await client.get(current)
                        except httpx.HTTPError as exc:
                            raise ProviderError(f'HTTP error: {exc.__class__.__name__}') from exc
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get('location')
                    if not location:
                        raise ProviderError('Redirect without Location')
                    current = await ensure_safe_url(redirect_url(current, location))
                    continue
                if response.status_code in {401, 403, 429}:
                    raise SourceBlockedError(f'Источник ограничил доступ: HTTP {response.status_code}')
                if response.status_code >= 400:
                    raise ProviderError(f'Источник вернул HTTP {response.status_code}')
                body = response.content
                if len(body) > self.settings.max_response_bytes:
                    raise ProviderError('Страница слишком большая для безопасного анализа')
                content_type = response.headers.get('content-type', '')
                return body.decode(response.encoding or 'utf-8', errors='replace'), current, content_type
        raise ProviderError('Слишком много redirect')

    async def fetch(self, url: str) -> ProductSnapshot:
        html, final_url, _content_type = await self._get_html(url)
        return self.parse_document(html, final_url)

    @staticmethod
    def _iter_jsonld(data):
        if isinstance(data, dict):
            if data.get('@type') == 'Product' or (isinstance(data.get('@type'), list) and 'Product' in data.get('@type', [])):
                yield data
            for value in data.values():
                yield from GenericProvider._iter_jsonld(value)
        elif isinstance(data, list):
            for value in data:
                yield from GenericProvider._iter_jsonld(value)

    @staticmethod
    def _availability(value: object) -> str:
        text = str(value or '').lower()
        if any(x in text for x in ('instock', 'in stock', 'available', 'в наличии')):
            return 'in_stock'
        if any(x in text for x in ('outofstock', 'out of stock', 'soldout', 'нет в наличии')):
            return 'out_of_stock'
        return 'unknown'

    @classmethod
    def parse_document(cls, html: str, url: str) -> ProductSnapshot:
        soup = BeautifulSoup(html, 'lxml')
        host = urlsplit(url).hostname or 'unknown'
        name: str | None = None
        image_url: str | None = None
        seller: str | None = None
        availability = 'unknown'
        old_price: Decimal | None = None
        canonical = url
        candidates: list[Candidate] = []

        canonical_tag = soup.find('link', rel=lambda v: v and 'canonical' in v)
        if canonical_tag and canonical_tag.get('href'):
            try:
                candidate_url = canonical_tag['href']
                if str(candidate_url).startswith(('http://', 'https://')):
                    canonical = normalize_url(str(candidate_url))
            except ValueError:
                pass

        for script in soup.find_all('script', attrs={'type': re.compile(r'ld\+json', re.I)}):
            raw = script.string or script.get_text(strip=True)
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            for product in cls._iter_jsonld(data):
                name = name or product.get('name')
                image = product.get('image')
                if isinstance(image, list):
                    image = image[0] if image else None
                if isinstance(image, dict):
                    image = image.get('url')
                image_url = image_url or image
                brand = product.get('brand')
                if isinstance(brand, dict):
                    seller = seller or brand.get('name')
                offers = product.get('offers')
                if isinstance(offers, dict):
                    offers = [offers]
                for offer in offers or []:
                    if not isinstance(offer, dict):
                        continue
                    price = parse_price(offer.get('price') or offer.get('lowPrice'))
                    currency = offer.get('priceCurrency')
                    if price is not None:
                        candidates.append(Candidate(price, currency, 0.99, 'jsonld'))
                    old_price = old_price or parse_price(offer.get('highPrice'))
                    availability = cls._availability(offer.get('availability')) if availability == 'unknown' else availability
                    offered_by = offer.get('seller')
                    if isinstance(offered_by, dict):
                        seller = seller or offered_by.get('name')

        def meta_content(*selectors: tuple[str, str]) -> str | None:
            for attr, value in selectors:
                tag = soup.find('meta', attrs={attr: value})
                if tag and tag.get('content'):
                    return str(tag['content']).strip()
            return None

        name = name or meta_content(('property', 'og:title'), ('name', 'twitter:title'))
        image_url = image_url or meta_content(('property', 'og:image'), ('name', 'twitter:image'))
        meta_price = meta_content(
            ('property', 'product:price:amount'), ('property', 'og:price:amount'),
            ('name', 'product:price:amount'), ('itemprop', 'price')
        )
        meta_currency = meta_content(
            ('property', 'product:price:currency'), ('property', 'og:price:currency'), ('itemprop', 'priceCurrency')
        )
        if (price := parse_price(meta_price)) is not None:
            candidates.append(Candidate(price, meta_currency, 0.90, 'meta'))

        itemprop_price = soup.find(attrs={'itemprop': 'price'})
        if itemprop_price:
            raw_price = itemprop_price.get('content') or itemprop_price.get_text(' ', strip=True)
            if (price := parse_price(raw_price)) is not None:
                curr_tag = soup.find(attrs={'itemprop': 'priceCurrency'})
                curr = curr_tag.get('content') if curr_tag else None
                candidates.append(Candidate(price, curr, 0.92, 'microdata'))

        fallback_selectors = [
            '[data-price]', '.price', '.product-price', '.sale-price', '.current-price',
            '[class*="price_current"]', '[class*="current-price"]', '[class*="product-price"]'
        ]
        for selector in fallback_selectors:
            for node in soup.select(selector)[:5]:
                raw = node.get('data-price') or node.get('content') or node.get_text(' ', strip=True)
                if (price := parse_price(raw)) is not None:
                    curr = 'RUB' if ('₽' in str(raw) or 'руб' in str(raw).lower()) else None
                    candidates.append(Candidate(price, curr, 0.62, f'html:{selector}'))

        if not name:
            title = soup.title.get_text(' ', strip=True) if soup.title else None
            name = title or host

        if not candidates:
            raise PriceNotFoundError('Не удалось достоверно определить цену')

        candidates.sort(key=lambda c: c.confidence, reverse=True)
        top = candidates[0]
        if top.confidence < 0.85:
            counts = Counter(c.price for c in candidates if c.confidence >= 0.60)
            corroborated = [c for c in candidates if counts[c.price] >= 2]
            if not corroborated:
                raise PriceNotFoundError('Цена найдена только с низкой уверенностью')
            top = sorted(corroborated, key=lambda c: c.confidence, reverse=True)[0]

        return ProductSnapshot(
            product_name=str(name).strip()[:500],
            current_price=top.price,
            old_price=old_price,
            currency=(top.currency or meta_currency or ('RUB' if '₽' in html[:200000] else None)),
            availability=availability,
            image_url=image_url,
            canonical_url=canonical,
            seller=seller,
            source=host,
            confidence=top.confidence,
        )
