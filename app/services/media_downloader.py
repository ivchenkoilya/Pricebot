from __future__ import annotations

import asyncio
import html
import json
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


class MediaDownloadError(RuntimeError):
    pass


SUPPORTED_HOSTS = {
    'youtube.com': 'YouTube',
    'youtu.be': 'YouTube',
    'tiktok.com': 'TikTok',
    'instagram.com': 'Instagram',
    'twitter.com': 'X / Twitter',
    'x.com': 'X / Twitter',
}


def _host(url: str) -> str:
    host = (urlparse(url).hostname or '').lower().strip('.')
    for prefix in ('www.', 'm.', 'music.'):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return host


def platform_for_url(url: str) -> str | None:
    host = _host(url)
    for suffix, platform in SUPPORTED_HOSTS.items():
        if host == suffix or host.endswith('.' + suffix):
            return platform
    return None


def is_media_url(url: str) -> bool:
    return platform_for_url(url) is not None


def media_intent(text: str) -> str:
    low = ' '.join((text or '').lower().split())
    if not low:
        return 'inspect'
    if any(word in low for word in ('mp3', 'аудио', 'звук', 'audio')) and any(
        word in low for word in ('скач', 'download', 'сохрани')
    ):
        return 'audio'
    if any(word in low for word in ('расшиф', 'транскрип', 'в текст', 'сделай текст', 'что говорит', 'что сказано')):
        return 'transcribe'
    if any(word in low for word in ('кратко', 'перескаж', 'о чем', 'о чём', 'summary', 'суть')):
        return 'summary'
    if any(word in low for word in ('главное', 'ключевые', 'основные мысли', 'main points')):
        return 'main'
    if any(word in low for word in ('объясни', 'простыми словами', 'что значит')):
        return 'plain'
    if any(word in low for word in ('скач', 'download', 'сохрани видео', 'видео файлом')):
        return 'video'
    return 'inspect'


@dataclass(slots=True)
class MediaInfo:
    url: str
    platform: str
    title: str
    author: str
    duration: int
    filesize: int | None
    thumbnail: str | None = None

    @property
    def duration_text(self) -> str:
        minutes, seconds = divmod(max(0, int(self.duration or 0)), 60)
        if minutes >= 60:
            hours, minutes = divmod(minutes, 60)
            return f'{hours}:{minutes:02d}:{seconds:02d}'
        return f'{minutes}:{seconds:02d}'

    @property
    def size_mb(self) -> float | None:
        return round(self.filesize / 1024 / 1024, 1) if self.filesize else None


class MediaDownloader:
    """Fast public-media helper with YouTube fallbacks and subtitle-first transcripts."""

    _UA = (
        'Mozilla/5.0 (Linux; Android 14; SM-S928B) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Mobile Safari/537.36'
    )

    def __init__(self, settings):
        self.settings = settings
        self.temp_dir = Path(settings.resolved_media_temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._info_cache: dict[str, tuple[float, dict, MediaInfo]] = {}
        self._transcript_cache: dict[str, tuple[float, str]] = {}
        self._transcript_tasks: dict[str, asyncio.Task] = {}

    def _common_opts(self) -> dict:
        # Node 22 + yt-dlp-ejs solves current YouTube JS challenges. Keep retries
        # deliberately low: Clarify's UX target is a result/error inside ~30 sec.
        return {
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'socket_timeout': 6,
            'retries': 0,
            'extractor_retries': 0,
            'fragment_retries': 1,
            'concurrent_fragment_downloads': 4,
            'restrictfilenames': True,
            'js_runtimes': {'node': {}},
            'http_headers': {'User-Agent': self._UA},
        }

    def _option_variants(self, url: str) -> list[dict]:
        base = self._common_opts()
        if platform_for_url(url) != 'YouTube':
            return [base]
        # web_safari currently exposes HLS paths that are less dependent on GVS
        # PO tokens; embedded is a useful public-video fallback. The default
        # client is last because cloud-host IPs are more often challenged there.
        return [
            base | {'extractor_args': {'youtube': {'player_client': ['web_safari']}}},
            base | {'extractor_args': {'youtube': {'player_client': ['web_embedded']}}},
            base | {'extractor_args': {'youtube': {'player_client': ['default', '-tv_simply']}}},
        ]

    def _cache_get(self, url: str) -> tuple[dict, MediaInfo] | None:
        cached = self._info_cache.get(url)
        if not cached:
            return None
        created, raw, info = cached
        if time.monotonic() - created > self.settings.media_metadata_cache_seconds:
            self._info_cache.pop(url, None)
            return None
        return raw, info

    def _cache_put(self, requested_url: str, raw: dict, info: MediaInfo) -> None:
        value = (time.monotonic(), raw, info)
        self._info_cache[requested_url] = value
        self._info_cache[info.url] = value

    async def inspect(self, url: str) -> MediaInfo:
        if not is_media_url(url):
            raise MediaDownloadError('Этот сайт не относится к поддерживаемым видеоплатформам.')
        cached = self._cache_get(url)
        if cached:
            return cached[1]
        try:
            raw, info = await asyncio.wait_for(
                asyncio.to_thread(self._inspect_sync, url),
                timeout=max(3, int(self.settings.media_inspect_timeout_seconds)),
            )
            self._cache_put(url, raw, info)
            return info
        except TimeoutError as exc:
            raise MediaDownloadError('Платформа отвечает слишком долго. Попробуй ещё раз через несколько секунд.') from exc
        except DownloadError as exc:
            raise MediaDownloadError(self._friendly_error(str(exc))) from exc
        except MediaDownloadError:
            raise
        except Exception as exc:
            raise MediaDownloadError(self._friendly_error(str(exc))) from exc

    def _inspect_sync(self, url: str) -> tuple[dict, MediaInfo]:
        last_error: Exception | None = None
        for opts in self._option_variants(url):
            try:
                with YoutubeDL(opts | {'skip_download': True}) as ydl:
                    raw = ydl.extract_info(url, download=False)
                if not raw:
                    continue
                if raw.get('_type') == 'playlist' and raw.get('entries'):
                    raw = next((item for item in raw['entries'] if item), raw)
                filesize = raw.get('filesize') or raw.get('filesize_approx')
                if not filesize:
                    requested = raw.get('requested_formats') or []
                    values = [(item or {}).get('filesize') or (item or {}).get('filesize_approx') for item in requested]
                    known = [int(value) for value in values if value]
                    filesize = sum(known) if known else None
                info = MediaInfo(
                    url=raw.get('webpage_url') or url,
                    platform=platform_for_url(url) or str(raw.get('extractor_key') or 'Video'),
                    title=(str(raw.get('title') or 'Видео').strip()[:300]),
                    author=(str(raw.get('uploader') or raw.get('channel') or raw.get('creator') or '').strip()[:200]),
                    duration=int(raw.get('duration') or 0),
                    filesize=int(filesize) if filesize else None,
                    thumbnail=raw.get('thumbnail'),
                )
                return raw, info
            except Exception as exc:  # try the next public YouTube client quickly
                last_error = exc
        if last_error:
            raise last_error
        raise MediaDownloadError('Не удалось получить данные видео.')

    async def _raw_info(self, url: str) -> tuple[dict, MediaInfo]:
        cached = self._cache_get(url)
        if cached:
            return cached
        await self.inspect(url)
        cached = self._cache_get(url)
        if not cached:
            raise MediaDownloadError('Не удалось сохранить метаданные видео.')
        return cached

    def prefetch_transcript(self, url: str) -> None:
        if not self.settings.media_fast_subtitles or platform_for_url(url) != 'YouTube':
            return
        existing = self._transcript_tasks.get(url)
        if existing and not existing.done():
            return
        task = asyncio.create_task(self.fast_transcript(url))
        self._transcript_tasks[url] = task
        task.add_done_callback(lambda _task: self._transcript_tasks.pop(url, None))

    async def fast_transcript(self, url: str) -> str:
        if not self.settings.media_fast_subtitles or platform_for_url(url) != 'YouTube':
            return ''
        cached = self._transcript_cache.get(url)
        if cached and time.monotonic() - cached[0] <= self.settings.media_metadata_cache_seconds:
            return cached[1]

        task = self._transcript_tasks.get(url)
        current = asyncio.current_task()
        if task and task is not current and not task.done():
            try:
                return await task
            except Exception:
                return ''

        try:
            raw, info = await self._raw_info(url)
            transcript = await asyncio.wait_for(
                self._fetch_caption_track(raw),
                timeout=max(2, int(self.settings.media_subtitle_timeout_seconds)),
            )
        except Exception:
            return ''
        if transcript:
            value = (time.monotonic(), transcript)
            self._transcript_cache[url] = value
            self._transcript_cache[info.url] = value
        return transcript

    async def _fetch_caption_track(self, raw: dict) -> str:
        tracks_by_lang: dict[str, list[dict]] = {}
        for source in (raw.get('subtitles') or {}, raw.get('automatic_captions') or {}):
            for language, tracks in source.items():
                if tracks and language not in tracks_by_lang:
                    tracks_by_lang[language] = tracks
        if not tracks_by_lang:
            return ''

        languages = list(tracks_by_lang)
        preferred: list[str] = []
        for prefix in ('ru', 'en'):
            preferred.extend(lang for lang in languages if lang.lower() == prefix)
            preferred.extend(lang for lang in languages if lang.lower().startswith(prefix + '-'))
        preferred.extend(lang for lang in languages if lang not in preferred)

        chosen: dict | None = None
        for language in preferred:
            tracks = tracks_by_lang.get(language) or []
            chosen = next((track for track in tracks if track.get('ext') == 'json3'), None)
            chosen = chosen or next((track for track in tracks if track.get('ext') == 'vtt'), None)
            if chosen:
                break
        if not chosen or not chosen.get('url'):
            return ''

        async with httpx.AsyncClient(
            timeout=float(self.settings.media_subtitle_timeout_seconds),
            follow_redirects=True,
            headers={'User-Agent': self._UA},
        ) as client:
            response = await client.get(chosen['url'])
            response.raise_for_status()
        if chosen.get('ext') == 'json3':
            return self._parse_json3(response.text)
        return self._parse_vtt(response.text)

    @staticmethod
    def _dedupe_lines(lines: list[str]) -> str:
        result: list[str] = []
        previous = ''
        for line in lines:
            clean = re.sub(r'\s+', ' ', html.unescape(line or '')).strip()
            if not clean or clean == previous:
                continue
            result.append(clean)
            previous = clean
        return ' '.join(result).strip()

    @classmethod
    def _parse_json3(cls, payload: str) -> str:
        try:
            data = json.loads(payload)
        except Exception:
            return ''
        lines: list[str] = []
        for event in data.get('events') or []:
            text = ''.join((segment or {}).get('utf8', '') for segment in event.get('segs') or [])
            if text:
                lines.append(text.replace('\n', ' '))
        return cls._dedupe_lines(lines)

    @classmethod
    def _parse_vtt(cls, payload: str) -> str:
        lines: list[str] = []
        for raw_line in (payload or '').splitlines():
            line = raw_line.strip()
            if not line or line == 'WEBVTT' or '-->' in line or line.isdigit():
                continue
            if line.startswith(('Kind:', 'Language:', 'NOTE', 'STYLE', 'Region:')):
                continue
            line = re.sub(r'<[^>]+>', '', line)
            lines.append(line)
        return cls._dedupe_lines(lines)

    async def download_video(self, url: str, *, max_mb: int | None = None, max_height: int | None = None) -> Path:
        limit_mb = int(max_mb or self.settings.media_max_file_mb)
        height = int(max_height or self.settings.media_video_max_height)
        return await self._download(url, kind='video', limit_mb=limit_mb, height=height)

    async def download_audio(self, url: str, *, max_mb: int | None = None) -> Path:
        limit_mb = int(max_mb or self.settings.media_max_file_mb)
        return await self._download(url, kind='audio', limit_mb=limit_mb, height=0)

    async def _download(self, url: str, *, kind: str, limit_mb: int, height: int) -> Path:
        prefix = self.temp_dir / f'media_{uuid.uuid4().hex}'
        try:
            path = await asyncio.to_thread(self._download_sync, url, prefix, kind, limit_mb, height)
            if path.stat().st_size > limit_mb * 1024 * 1024:
                path.unlink(missing_ok=True)
                raise MediaDownloadError(f'Файл больше лимита {limit_mb} МБ.')
            return path
        except DownloadError as exc:
            self.cleanup_prefix(prefix)
            raise MediaDownloadError(self._friendly_error(str(exc))) from exc
        except MediaDownloadError:
            self.cleanup_prefix(prefix)
            raise
        except Exception as exc:
            self.cleanup_prefix(prefix)
            raise MediaDownloadError(self._friendly_error(str(exc))) from exc

    def _download_sync(self, url: str, prefix: Path, kind: str, limit_mb: int, height: int) -> Path:
        last_error: Exception | None = None
        for base_opts in self._option_variants(url):
            self.cleanup_prefix(prefix)
            opts = dict(base_opts)
            opts.update({
                'outtmpl': str(prefix) + '.%(ext)s',
                'max_filesize': limit_mb * 1024 * 1024,
            })
            if kind == 'audio':
                opts.update({
                    'format': 'bestaudio/best[height<=360]/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '160',
                    }],
                })
            else:
                opts.update({
                    'format': (
                        f'best[height<={height}]/'
                        f'bestvideo[height<={height}]+bestaudio/'
                        f'best'
                    ),
                    'merge_output_format': 'mp4',
                })
            try:
                with YoutubeDL(opts) as ydl:
                    ydl.download([url])
                candidates = [
                    path for path in prefix.parent.glob(prefix.name + '.*')
                    if path.is_file() and path.suffix not in {'.part', '.ytdl'}
                ]
                if candidates:
                    return max(candidates, key=lambda path: path.stat().st_size)
            except Exception as exc:
                last_error = exc
        if last_error:
            raise last_error
        raise MediaDownloadError('Не получилось получить готовый файл.')

    @staticmethod
    def cleanup(path: Path | None) -> None:
        if path:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def cleanup_prefix(prefix: Path) -> None:
        for path in prefix.parent.glob(prefix.name + '.*'):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def safe_filename(title: str, suffix: str) -> str:
        clean = re.sub(r'[^\w\-. ]+', '_', title or 'video', flags=re.UNICODE).strip(' ._')[:80] or 'video'
        return clean + suffix

    @staticmethod
    def _friendly_error(raw: str) -> str:
        low = (raw or '').lower()
        if any(word in low for word in ('confirm you’re not a bot', "confirm you're not a bot", 'sign in to confirm', 'po token', 'http error 403')):
            return 'YouTube временно отклонил запрос сервера. Clarify попробовал запасные публичные способы, но ролик сейчас не отдаётся.'
        if any(word in low for word in ('private video', 'private account', 'members-only', 'members only')):
            return 'Видео приватное или доступно только участникам. Clarify работает только с публичными видео.'
        if any(word in low for word in ('login required', 'age-restricted', 'age restricted')):
            return 'Для этого видео платформа требует авторизацию. Clarify работает только с публично доступными роликами без входа.'
        if any(word in low for word in ('copyright', 'drm', 'paid', 'premium')):
            return 'Это видео ограничено правообладателем или доступно только по подписке.'
        if any(word in low for word in ('unavailable', 'not available', 'removed', 'deleted')):
            return 'Видео недоступно или было удалено.'
        if 'filesize' in low or 'file is larger' in low:
            return 'Видео слишком большое для загрузки через Clarify.'
        return 'Не получилось получить видео. Возможно, платформа временно ограничила сервер или изменила защиту.'
