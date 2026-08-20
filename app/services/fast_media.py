from __future__ import annotations

import asyncio
import re
import time
from urllib.parse import parse_qs, urlparse

import httpx

from app.services.media_downloader import MediaDownloadError, MediaDownloader, MediaInfo, platform_for_url


_YOUTUBE_ID_RE = re.compile(r'^[A-Za-z0-9_-]{6,20}$')


def youtube_video_id(url: str) -> str:
    """Extract a public YouTube video id from watch, youtu.be or Shorts URLs."""
    try:
        parsed = urlparse(url)
    except Exception:
        return ''
    host = (parsed.hostname or '').lower()
    if host.startswith('www.'):
        host = host[4:]
    candidate = ''
    if host == 'youtu.be':
        candidate = parsed.path.strip('/').split('/', 1)[0]
    elif host.endswith('youtube.com'):
        if parsed.path == '/watch':
            candidate = (parse_qs(parsed.query).get('v') or [''])[0]
        elif parsed.path.startswith('/shorts/') or parsed.path.startswith('/embed/'):
            parts = parsed.path.strip('/').split('/')
            candidate = parts[1] if len(parts) > 1 else ''
    return candidate if _YOUTUBE_ID_RE.match(candidate or '') else ''


class FastMediaDownloader(MediaDownloader):
    """Latency-first facade for public media links.

    YouTube frequently rate-limits or blocks datacenter IPs. `MEDIA_PROXY_URL`
    lets the same proxy be used consistently for oEmbed, subtitles and yt-dlp.
    Without a proxy the bot still uses the direct fast path and fails quickly
    instead of keeping the Telegram user waiting for minutes.
    """

    def __init__(self, settings):
        super().__init__(settings)
        self._fast_info_cache: dict[str, tuple[float, MediaInfo]] = {}
        self._direct_transcript_cache: dict[str, tuple[float, str]] = {}
        self._direct_tasks: dict[str, asyncio.Task] = {}

    @property
    def _proxy(self) -> str | None:
        value = str(getattr(self.settings, 'media_proxy_url', '') or '').strip()
        return value or None

    def _common_opts(self) -> dict:
        opts = super()._common_opts()
        if self._proxy:
            opts['proxy'] = self._proxy
        # Fewer retries/clients are deliberate: the whole UX budget is <30 sec.
        opts['socket_timeout'] = 5
        opts['retries'] = 0
        opts['extractor_retries'] = 0
        opts['fragment_retries'] = 0
        return opts

    def _fast_cache_get(self, url: str) -> MediaInfo | None:
        item = self._fast_info_cache.get(url)
        if not item:
            return None
        created, info = item
        if time.monotonic() - created > self.settings.media_metadata_cache_seconds:
            self._fast_info_cache.pop(url, None)
            return None
        return info

    def _remember_fast_info(self, url: str, info: MediaInfo) -> MediaInfo:
        self._fast_info_cache[url] = (time.monotonic(), info)
        if info.url and info.url != url:
            self._fast_info_cache[info.url] = (time.monotonic(), info)
        return info

    @staticmethod
    def _placeholder(url: str, platform: str) -> MediaInfo:
        return MediaInfo(
            url=url,
            platform=platform,
            title=f'{platform} видео',
            author='',
            duration=0,
            filesize=None,
            thumbnail=None,
        )

    async def inspect(self, url: str) -> MediaInfo:
        platform = platform_for_url(url)
        if not platform:
            return await super().inspect(url)

        cached = self._fast_cache_get(url)
        if cached:
            return cached

        if platform == 'YouTube':
            try:
                timeout = min(2.5, max(1.5, float(self.settings.media_inspect_timeout_seconds)))
                async with httpx.AsyncClient(
                    timeout=timeout,
                    follow_redirects=True,
                    proxy=self._proxy,
                    headers={'User-Agent': self._UA},
                ) as client:
                    response = await client.get(
                        'https://www.youtube.com/oembed',
                        params={'url': url, 'format': 'json'},
                    )
                    response.raise_for_status()
                    data = response.json()
                return self._remember_fast_info(
                    url,
                    MediaInfo(
                        url=url,
                        platform='YouTube',
                        title=str(data.get('title') or 'YouTube видео').strip()[:300],
                        author=str(data.get('author_name') or '').strip()[:200],
                        duration=0,
                        filesize=None,
                        thumbnail=data.get('thumbnail_url'),
                    ),
                )
            except Exception:
                return self._remember_fast_info(url, self._placeholder(url, 'YouTube'))

        try:
            return self._remember_fast_info(url, await super().inspect(url))
        except MediaDownloadError as exc:
            text = str(exc).lower()
            if any(marker in text for marker in ('слишком долго', 'временно', 'изменила защиту', 'ограничила сервер')):
                return self._remember_fast_info(url, self._placeholder(url, platform))
            raise

    def prefetch_transcript(self, url: str) -> None:
        if platform_for_url(url) != 'YouTube' or not self.settings.media_fast_subtitles:
            return
        existing = self._direct_tasks.get(url)
        if existing and not existing.done():
            return
        task = asyncio.create_task(self.fast_transcript(url))
        self._direct_tasks[url] = task
        task.add_done_callback(lambda _task: self._direct_tasks.pop(url, None))

    async def fast_transcript(self, url: str) -> str:
        if platform_for_url(url) != 'YouTube' or not self.settings.media_fast_subtitles:
            return await super().fast_transcript(url)
        cached = self._direct_transcript_cache.get(url)
        if cached and time.monotonic() - cached[0] <= self.settings.media_metadata_cache_seconds:
            return cached[1]

        task = self._direct_tasks.get(url)
        current = asyncio.current_task()
        if task and task is not current and not task.done():
            try:
                return await asyncio.wait_for(
                    asyncio.shield(task),
                    timeout=max(2, int(self.settings.media_subtitle_timeout_seconds)),
                )
            except Exception:
                pass

        video_id = youtube_video_id(url)
        if video_id:
            try:
                text = await asyncio.wait_for(
                    asyncio.to_thread(self._youtube_transcript_sync, video_id),
                    timeout=max(2, int(self.settings.media_subtitle_timeout_seconds)),
                )
                if text:
                    self._direct_transcript_cache[url] = (time.monotonic(), text)
                    return text
            except Exception:
                pass
        return ''

    def _youtube_transcript_sync(self, video_id: str) -> str:
        from youtube_transcript_api import YouTubeTranscriptApi

        if self._proxy:
            from youtube_transcript_api.proxies import GenericProxyConfig

            api = YouTubeTranscriptApi(
                proxy_config=GenericProxyConfig(
                    http_url=self._proxy,
                    https_url=self._proxy,
                )
            )
        else:
            api = YouTubeTranscriptApi()

        transcript = api.fetch(video_id, languages=['ru', 'en'])
        parts: list[str] = []
        for snippet in transcript:
            value = getattr(snippet, 'text', '')
            value = re.sub(r'\s+', ' ', str(value or '')).strip()
            if value and (not parts or value != parts[-1]):
                parts.append(value)
        return ' '.join(parts).strip()

    def _option_variants(self, url: str) -> list[dict]:
        if platform_for_url(url) != 'YouTube':
            return super()._option_variants(url)
        base = self._common_opts()
        # Keep only two fast attempts. Four sequential extractor clients were
        # enough to consume the entire 30-second budget on blocked Amvera IPs.
        return [
            base | {'extractor_args': {'youtube': {'player_client': ['web_safari']}}},
            base | {'extractor_args': {'youtube': {'player_client': ['web_embedded']}}},
        ]
