from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

from app.config.settings import Settings
from app.trackers.generic import GenericProvider
from app.utils.url import ensure_safe_url

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

    Direct HTTP is attempted first. If the page is dynamic, empty, or blocked,
    Jina Reader can be used as a browser-rendered public-page fallback. The
    original target URL is always SSRF-validated before either path is used.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.generic = GenericProvider(settings)

    async def read(self, url: str) -> PageReadResult:
        safe_url = await ensure_safe_url(url)
        errors: list[str] = []

        try:
            html, final_url, _content_type = await self.generic._get_html(safe_url)
            direct = self._from_html(safe_url, final_url, html)
            if self._useful(direct):
                return direct
            errors.append('direct: страница почти пустая')
        except Exception as exc:
            errors.append(f'direct: {exc.__class__.__name__}')

        if self.settings.page_reader_jina_enabled:
            try:
                rendered = await self._read_jina(safe_url)
                if self._useful(rendered):
                    return rendered
                errors.append('reader: пустой ответ')
            except Exception as exc:
                logger.info('page reader fallback failed host=%s type=%s', urlsplit(safe_url).hostname, exc.__class__.__name__)
                errors.append(f'reader: {exc.__class__.__name__}')

        raise PageReadError('; '.join(errors) if errors else 'Не удалось прочитать страницу')

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

        text = response.text.strip()
        title: str | None = None
        final_url = target_url
        for line in text.splitlines()[:30]:
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
            source='jina-reader',
        )

    def _useful(self, result: PageReadResult) -> bool:
        low = result.text.lower()
        blocked = (
            'access denied', 'доступ ограничен', 'captcha', 'проверка браузера',
            'подтвердите, что вы не робот', 'too many requests',
        )
        if any(marker in low for marker in blocked):
            return False
        return len(result.text.strip()) >= self.settings.page_reader_min_chars

    def _limit(self, value: str) -> str:
        clean = re.sub(r'\n{4,}', '\n\n\n', value).strip()
        return clean[: self.settings.page_reader_max_chars]

    @staticmethod
    def _clean(value: str | None) -> str:
        return re.sub(r'\s+', ' ', value or '').strip()
