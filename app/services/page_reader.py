from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlsplit

import httpx
from bs4 import BeautifulSoup

from app.config.settings import Settings
from app.trackers.generic import GenericProvider
from app.utils.url import ensure_safe_url, redirect_url

logger = logging.getLogger(__name__)


class PageReadError(RuntimeError):
    pass


@dataclass(slots=True)
class PageReadResult:
    requested_url: str
    final_url: str
    title: str | None
    description: str | None
    text: str
    source: str

    @property
    def host(self) -> str:
        return urlsplit(self.final_url).hostname or urlsplit(self.requested_url).hostname or 'unknown'


class PageReader:
    """Read public web pages for LLM context without bypassing access controls.

    Flow:
    1. validate the user URL and resolve ordinary HTTP redirects;
    2. try direct HTML extraction;
    3. try Jina Reader for dynamic public pages;
    4. if a Jina key is configured, use Jina web search as a final index fallback;
    5. for an Ozon long product URL, retain product identity from its public slug/id.

    CAPTCHA/login/access controls are never bypassed.
    """

    BLOCKED_MARKERS = (
        'access denied',
        'доступ ограничен',
        'captcha',
        'проверка браузера',
        'подтвердите, что вы не робот',
        'too many requests',
        'antibot challenge page',
        'похоже, нет соединения',
        'нет соединения',
        'проверьте подключение к интернету',
        'что-то пошло не так',
        'something went wrong',
    )

    OZON_PRODUCT_RE = re.compile(r'/product/([^/?]+?)-(\d{6,})(?:/|$)', re.I)

    def __init__(self, settings: Settings):
        self.settings = settings
        self.generic = GenericProvider(settings)

    async def read(self, url: str) -> PageReadResult:
        safe_url = await ensure_safe_url(url)
        errors: list[str] = []

        resolved_url = safe_url
        try:
            resolved_url = await self._resolve_redirect_target(safe_url)
        except Exception as exc:
            errors.append(f'redirect: {exc.__class__.__name__}')

        try:
            html, final_url, _content_type = await self.generic._get_html(resolved_url)
            direct = self._from_html(safe_url, final_url, html)
            if self._useful(direct):
                return direct
            errors.append('direct: error/empty page')
        except Exception as exc:
            errors.append(f'direct: {exc.__class__.__name__}')

        if self.settings.page_reader_jina_enabled:
            try:
                rendered = await self._read_jina(resolved_url)
                if self._useful(rendered):
                    return rendered
                errors.append('reader: Ozon/error page')
            except Exception as exc:
                logger.info(
                    'page reader fallback failed host=%s type=%s',
                    urlsplit(resolved_url).hostname,
                    exc.__class__.__name__,
                )
                errors.append(f'reader: {exc.__class__.__name__}')

        # Jina's search endpoint is not available anonymously. If the user has
        # supplied a Jina key, use the search index as a last public-data fallback.
        if self.settings.jina_reader_api_key.strip():
            try:
                searched = await self._search_jina(resolved_url)
                if self._useful(searched):
                    return searched
                errors.append('search: empty/error result')
            except Exception as exc:
                logger.info(
                    'page search fallback failed host=%s type=%s',
                    urlsplit(resolved_url).hostname,
                    exc.__class__.__name__,
                )
                errors.append(f'search: {exc.__class__.__name__}')

        # Even when Ozon blocks the page body, a normal HTTP redirect often
        # reveals the canonical /product/<slug>-<id>/ URL. The slug is public
        # product identity, not a price source, so it is safe to preserve it.
        from_url = self._from_ozon_product_url(safe_url, resolved_url)
        if from_url is not None:
            return from_url

        raise PageReadError('; '.join(errors) if errors else 'Не удалось прочитать страницу')

    async def _resolve_redirect_target(self, url: str) -> str:
        """Resolve standard redirects while validating every hop for SSRF.

        The final response body is intentionally not consumed. This lets us keep
        a useful long product URL even when the final store page answers 403/429.
        """
        current = await ensure_safe_url(url)
        timeout = httpx.Timeout(self.settings.request_timeout)
        headers = {
            'User-Agent': self.settings.provider_user_agent,
            'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
            'Accept-Language': 'ru,en;q=0.8',
        }
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, headers=headers) as client:
            for _ in range(6):
                async with client.stream('GET', current) as response:
                    if response.status_code not in {301, 302, 303, 307, 308}:
                        return current
                    location = response.headers.get('location')
                    if not location:
                        return current
                    current = await ensure_safe_url(redirect_url(current, location))
        return current

    def _from_html(self, requested_url: str, final_url: str, html: str) -> PageReadResult:
        soup = BeautifulSoup(html, 'lxml')

        def meta_content(*pairs: tuple[str, str]) -> str | None:
            for attr, value in pairs:
                node = soup.find('meta', attrs={attr: value})
                if node and node.get('content'):
                    return self._clean(str(node['content']))
            return None

        h1 = soup.find('h1')
        title = self._clean(h1.get_text(' ', strip=True)) if h1 else None
        title = title or meta_content(('property', 'og:title'), ('name', 'twitter:title'))
        if not title and soup.title:
            title = self._clean(soup.title.get_text(' ', strip=True))

        description = meta_content(
            ('name', 'description'),
            ('property', 'og:description'),
            ('name', 'twitter:description'),
        )

        structured: list[str] = []
        for script in soup.find_all('script', attrs={'type': re.compile(r'ld\+json', re.I)})[:8]:
            raw = script.string or script.get_text(' ', strip=True)
            raw = self._clean(raw)
            if raw:
                structured.append(raw[:5000])

        for node in soup(['script', 'style', 'noscript', 'svg', 'template']):
            node.decompose()
        visible = '\n'.join(self._clean(s) for s in soup.stripped_strings if self._clean(s))

        chunks = []
        if title:
            chunks.append(f'Title: {title}')
        if description:
            chunks.append(f'Description: {description}')
        if structured:
            chunks.append('Structured data:\n' + '\n'.join(structured))
        if visible:
            chunks.append('Visible page text:\n' + visible)
        text = '\n\n'.join(chunks)

        return PageReadResult(
            requested_url=requested_url,
            final_url=final_url,
            title=title,
            description=description,
            text=self._limit(text),
            source='direct',
        )

    async def _read_jina(self, target_url: str) -> PageReadResult:
        endpoint = f'https://r.jina.ai/{target_url}'
        headers = {
            'Accept': 'text/plain',
            'User-Agent': self.settings.provider_user_agent,
            'X-Remove-Selector': 'nav,footer,.sidebar,#ads,.ads',
            'X-Timeout': str(max(5, int(self.settings.page_reader_timeout))),
        }
        if self.settings.jina_reader_api_key.strip():
            headers['Authorization'] = f'Bearer {self.settings.jina_reader_api_key.strip()}'

        timeout = httpx.Timeout(self.settings.page_reader_timeout)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
            response = await client.get(endpoint)
        if response.status_code in {401, 403, 429}:
            raise PageReadError(f'Reader ограничил запрос: HTTP {response.status_code}')
        if response.status_code >= 400:
            raise PageReadError(f'Reader вернул HTTP {response.status_code}')

        return await self._from_jina_text(target_url, response.text, 'jina-reader')

    async def _search_jina(self, target_url: str) -> PageReadResult:
        product_id = self._ozon_product_id(target_url)
        if product_id:
            query = f'site:ozon.ru/product {product_id}'
        else:
            query = f'"{target_url}"'
        endpoint = f'https://s.jina.ai/?q={quote(query)}'
        headers = {
            'Accept': 'text/plain',
            'User-Agent': self.settings.provider_user_agent,
            'Authorization': f'Bearer {self.settings.jina_reader_api_key.strip()}',
        }
        timeout = httpx.Timeout(self.settings.page_reader_timeout)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
            response = await client.get(endpoint)
        if response.status_code in {401, 403, 429}:
            raise PageReadError(f'Search ограничил запрос: HTTP {response.status_code}')
        if response.status_code >= 400:
            raise PageReadError(f'Search вернул HTTP {response.status_code}')
        result = await self._from_jina_text(target_url, response.text, 'jina-search')
        # Search results can contain unrelated products; require the product id
        # when one is known from Ozon's canonical URL.
        if product_id and product_id not in result.text:
            raise PageReadError('Search не подтвердил Ozon product ID')
        return result

    async def _from_jina_text(self, target_url: str, raw_text: str, source: str) -> PageReadResult:
        text = raw_text.strip()
        title: str | None = None
        final_url = target_url
        for line in text.splitlines()[:40]:
            clean = self._clean(line.strip())
            lower = clean.lower()
            if lower.startswith('title:'):
                candidate = self._clean(clean.split(':', 1)[1])
                if candidate:
                    title = candidate
            elif lower.startswith('url source:'):
                candidate = clean.split(':', 1)[1].strip()
                if candidate.startswith(('http://', 'https://')):
                    try:
                        final_url = await ensure_safe_url(candidate)
                    except Exception:
                        final_url = target_url
            elif title is None:
                candidate = self._clean(clean.lstrip('#').strip())
                if candidate and not lower.startswith(('published time:', 'markdown content:')):
                    title = candidate

        return PageReadResult(
            requested_url=target_url,
            final_url=final_url,
            title=title,
            description=None,
            text=self._limit(text),
            source=source,
        )

    def _from_ozon_product_url(self, requested_url: str, resolved_url: str) -> PageReadResult | None:
        match = self.OZON_PRODUCT_RE.search(urlsplit(resolved_url).path)
        if not match:
            return None
        slug, product_id = match.groups()
        words = re.sub(r'-+', ' ', unquote(slug)).strip()
        title = words[:1].upper() + words[1:] if words else f'Ozon товар {product_id}'
        text = f'Ozon product URL: {resolved_url}\nProduct ID: {product_id}\nProduct slug: {words}'
        return PageReadResult(
            requested_url=requested_url,
            final_url=resolved_url,
            title=title,
            description=None,
            text=text,
            source='resolved-url',
        )

    def _useful(self, result: PageReadResult) -> bool:
        low = f'{result.title or ""}\n{result.text}'.lower()
        if any(marker in low for marker in self.BLOCKED_MARKERS):
            return False
        return len(result.text.strip()) >= self.settings.page_reader_min_chars

    @classmethod
    def _ozon_product_id(cls, url: str) -> str | None:
        match = cls.OZON_PRODUCT_RE.search(urlsplit(url).path)
        return match.group(2) if match else None

    def _limit(self, value: str) -> str:
        clean = re.sub(r'\n{4,}', '\n\n\n', value).strip()
        return clean[: self.settings.page_reader_max_chars]

    @staticmethod
    def _clean(value: str | None) -> str:
        return re.sub(r'\s+', ' ', value or '').strip()
