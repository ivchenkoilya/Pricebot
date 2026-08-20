from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

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
    def __init__(self, settings):
        self.settings = settings
        self.temp_dir = Path(settings.media_temp_dir or Path(settings.data_dir, 'tmp', 'media'))
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def _common_opts(self) -> dict:
        return {
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'socket_timeout': 20,
            'retries': 2,
            'fragment_retries': 2,
            'concurrent_fragment_downloads': 2,
            'restrictfilenames': True,
        }

    async def inspect(self, url: str) -> MediaInfo:
        if not is_media_url(url):
            raise MediaDownloadError('Этот сайт не относится к поддерживаемым видеоплатформам.')
        try:
            return await asyncio.to_thread(self._inspect_sync, url)
        except DownloadError as exc:
            raise MediaDownloadError(self._friendly_error(str(exc))) from exc
        except Exception as exc:
            raise MediaDownloadError(self._friendly_error(str(exc))) from exc

    def _inspect_sync(self, url: str) -> MediaInfo:
        opts = self._common_opts() | {'skip_download': True}
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            raise MediaDownloadError('Не удалось получить данные видео.')
        if info.get('_type') == 'playlist' and info.get('entries'):
            info = next((item for item in info['entries'] if item), info)
        filesize = info.get('filesize') or info.get('filesize_approx')
        if not filesize:
            requested = info.get('requested_formats') or []
            values = [(item or {}).get('filesize') or (item or {}).get('filesize_approx') for item in requested]
            known = [int(value) for value in values if value]
            filesize = sum(known) if known else None
        return MediaInfo(
            url=info.get('webpage_url') or url,
            platform=platform_for_url(url) or str(info.get('extractor_key') or 'Video'),
            title=(str(info.get('title') or 'Видео').strip()[:300]),
            author=(str(info.get('uploader') or info.get('channel') or info.get('creator') or '').strip()[:200]),
            duration=int(info.get('duration') or 0),
            filesize=int(filesize) if filesize else None,
            thumbnail=info.get('thumbnail'),
        )

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
        opts = self._common_opts()
        opts.update({
            'outtmpl': str(prefix) + '.%(ext)s',
            'max_filesize': limit_mb * 1024 * 1024,
        })
        if kind == 'audio':
            opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        else:
            opts.update({
                'format': (
                    f'bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/'
                    f'best[height<={height}][ext=mp4]/best[height<={height}]/best'
                ),
                'merge_output_format': 'mp4',
            })
        with YoutubeDL(opts) as ydl:
            ydl.download([url])
        candidates = [
            path for path in prefix.parent.glob(prefix.name + '.*')
            if path.is_file() and path.suffix not in {'.part', '.ytdl'}
        ]
        if not candidates:
            raise MediaDownloadError('Не получилось получить готовый файл.')
        return max(candidates, key=lambda path: path.stat().st_size)

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
        if any(word in low for word in ('private video', 'private account', 'login required', 'sign in')):
            return 'Видео недоступно без авторизации. Clarify работает только с публичными видео.'
        if any(word in low for word in ('copyright', 'drm', 'paid', 'members-only', 'premium')):
            return 'Это видео ограничено правообладателем или доступно только по подписке.'
        if any(word in low for word in ('unavailable', 'not available', 'removed', 'deleted')):
            return 'Видео недоступно или было удалено.'
        if 'filesize' in low or 'file is larger' in low:
            return 'Видео слишком большое для загрузки через Clarify.'
        return 'Не получилось получить видео. Возможно, платформа изменила защиту или ролик ограничен.'
