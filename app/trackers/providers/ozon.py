from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup

from app.config.settings import Settings
from app.trackers.base import PriceNotFoundError, ProductSnapshot, SourceBlockedError
from app.trackers.generic import GenericProvider
from app.utils.money import parse_price
from app.utils.url import normalize_url


OZON_HOSTS = {'ozon.ru', 'www.ozon.ru', 'm.ozon.ru'}
PRICE_RE = re.compile(
    r'(?<!\d)(\d{1,3}(?:[\s\u00a0\u2009\u202f]\d{3})+(?:[.,]\d{1,2})?|\d{2,9}(?:[.,]\d{1,2})?)\s*₽',
    re.I,
)
PRODUCT_ID_RE = re.compile(r'/product/(?:[^/?]*?-)?(\d{6,})(?:/|$)', re.I)


@dataclass(slots=True)
class VisiblePrice:
    line_index: int
    value: Decimal
    raw: str


def is_ozon_url(url: str) -> bool:
    try:
        host = (urlsplit(normalize_url(url)).hostname or '').lower()
    except ValueError:
        return False
    return host in OZON_HOSTS or host.endswith('.ozon.ru')


def ozon_product_id(url: str) -> str | None:
    match = PRODUCT_ID_RE.search(urlsplit(url).path)
    return match.group(1) if match else None


def canonicalize_ozon_url(url: str) -> str:
    normalized = normalize_url(url)
    parts = urlsplit(normalized)
    host = (parts.hostname or '').lower()
    if host not in OZON_HOSTS and not host.endswith('.ozon.ru'):
        return normalized
    # Ozon product identity lives in the product path/id. Marketing/search query
    # parameters must not create duplicate Product rows.
    return urlunsplit(('https', 'www.ozon.ru', parts.path or '/', '', ''))


def _clean_title(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r'\s+', ' ', value).strip()
    text = re.sub(r'\s+купить\s+(?:c|с)\s+доставкой.*$', '', text, flags=re.I)
    text = re.sub(r'\s+купить\s+на\s+OZON.*$', '', text, flags=re.I)
    return text[:500] or None


def _visible_prices(lines: list[str]) -> list[VisiblePrice]:
    result: list[VisiblePrice] = []
    for idx, line in enumerate(lines):
        for match in PRICE_RE.finditer(line):
            raw = match.group(0)
            value = parse_price(raw)
            if value is not None:
                result.append(VisiblePrice(idx, value, raw))
    return result


def _first_line(lines: list[str], needle: str) -> int | None:
    needle = needle.lower()
    for idx, line in enumerate(lines):
        if needle in line.lower():
            return idx
    return None


def _candidate_is_auxiliary(lines: list[str], candidate: VisiblePrice) -> bool:
    context = ' '.join(lines[max(0, candidate.line_index - 2): candidate.line_index + 3]).lower()
    bad = (
        'доплата', 'таможенн', 'в месяц', 'рассроч', 'кешбэк', 'кэшбэк',
        'есть дешевле', 'есть быстрее', 'от ', 'экономия', 'балл',
    )
    return any(marker in context for marker in bad)


def _pick_current_and_old(lines: list[str], candidates: list[VisiblePrice]) -> tuple[Decimal | None, Decimal | None, float]:
    if not candidates:
        return None, None, 0.0

    other_banks = _first_line(lines, 'с другими банками')
    with_banks = _first_line(lines, 'с банками')
    buy = _first_line(lines, 'в корзину')
    if buy is None:
        buy = _first_line(lines, 'купить сейчас')

    usable = [c for c in candidates if not _candidate_is_auxiliary(lines, c)]
    if not usable:
        return None, None, 0.0

    # Prefer the ordinary-card price when Ozon explicitly labels it. Ozon often
    # shows a lower bank/card promo and an old crossed-out price in the same block;
    # taking the minimum in the ordinary-bank segment avoids mistaking the old
    # crossed-out amount for the current price.
    if other_banks is not None:
        start = (with_banks + 1) if with_banks is not None and with_banks < other_banks else max(0, other_banks - 8)
        segment = [c for c in usable if start <= c.line_index <= other_banks]
        if segment:
            current = min(c.value for c in segment)
            higher = [c.value for c in segment if c.value > current * Decimal('1.03')]
            old = max(higher) if higher else None
            return current, old, 0.96

    # Otherwise stay in the primary purchase area and ignore recommendation
    # prices that appear after "Есть дешевле/быстрее".
    end = buy if buy is not None else min(len(lines) - 1, max(c.line_index for c in usable))
    before_buy = [c for c in usable if c.line_index <= end]
    if before_buy:
        # Restrict to the last price cluster before the buy button; page headers
        # and recommendation widgets may contain unrelated amounts earlier.
        last_idx = max(c.line_index for c in before_buy)
        cluster = [c for c in before_buy if c.line_index >= max(0, last_idx - 10)]
        current = min(c.value for c in cluster)
        higher = [c.value for c in cluster if c.value > current * Decimal('1.03')]
        old = max(higher) if higher else None
        return current, old, 0.91 if buy is not None else 0.82

    return None, None, 0.0


class OzonProvider(GenericProvider):
    name = 'ozon'

    def __init__(self, settings: Settings):
        super().__init__(settings)

    async def supports(self, url: str) -> bool:
        return is_ozon_url(url)

    async def fetch(self, url: str) -> ProductSnapshot:
        html, final_url, _content_type = await self._get_html(url)
        final_url = canonicalize_ozon_url(final_url)

        # Structured data remains the strongest source whenever Ozon provides it.
        try:
            snapshot = GenericProvider.parse_document(html, final_url)
            snapshot.source = 'ozon.ru'
            snapshot.canonical_url = canonicalize_ozon_url(snapshot.canonical_url or final_url)
            snapshot.product_name = _clean_title(snapshot.product_name) or 'Ozon товар'
            return snapshot
        except PriceNotFoundError:
            return self.parse_ozon_document(html, final_url)

    @classmethod
    def parse_ozon_document(cls, html: str, final_url: str) -> ProductSnapshot:
        soup = BeautifulSoup(html, 'lxml')
        lines = [re.sub(r'\s+', ' ', value).strip() for value in soup.stripped_strings]
        lines = [value for value in lines if value]
        joined = '\n'.join(lines)
        low = joined.lower()

        blocked_markers = (
            'доступ ограничен', 'слишком много запросов', 'captcha',
            'подтвердите, что вы не робот', 'проверка браузера',
        )
        if any(marker in low for marker in blocked_markers):
            raise SourceBlockedError('Ozon ограничил автоматическую проверку страницы')

        h1 = soup.find('h1')
        name = _clean_title(h1.get_text(' ', strip=True) if h1 else None)
        if not name:
            og = soup.find('meta', attrs={'property': 'og:title'})
            name = _clean_title(str(og.get('content')) if og and og.get('content') else None)
        if not name and soup.title:
            name = _clean_title(soup.title.get_text(' ', strip=True))

        image_url: str | None = None
        og_image = soup.find('meta', attrs={'property': 'og:image'})
        if og_image and og_image.get('content'):
            image_url = str(og_image['content']).strip()

        canonical = final_url
        canonical_tag = soup.find('link', rel=lambda value: value and 'canonical' in value)
        if canonical_tag and canonical_tag.get('href'):
            candidate = str(canonical_tag['href'])
            if is_ozon_url(candidate):
                canonical = canonicalize_ozon_url(candidate)
        canonical = canonicalize_ozon_url(canonical)

        candidates = _visible_prices(lines)
        current, old, confidence = _pick_current_and_old(lines, candidates)
        if current is None or confidence < 0.85:
            raise PriceNotFoundError('Ozon: не удалось достоверно выделить основную цену товара')

        availability = 'unknown'
        if any(marker in low for marker in ('нет в наличии', 'товар закончился', 'распродано')):
            availability = 'out_of_stock'
        elif any(marker in low for marker in ('в корзину', 'купить сейчас')):
            availability = 'in_stock'

        if not name:
            product_id = ozon_product_id(canonical)
            name = f'Ozon товар {product_id}' if product_id else 'Ozon товар'

        return ProductSnapshot(
            product_name=name,
            current_price=current,
            old_price=old,
            currency='RUB',
            availability=availability,
            image_url=image_url,
            canonical_url=canonical,
            seller=None,
            source='ozon.ru',
            confidence=confidence,
        )
