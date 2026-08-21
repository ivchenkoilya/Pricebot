from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from app.config.settings import Settings


logger = logging.getLogger(__name__)


class SpeechToTextProvider:
    async def transcribe(self, path: str, language: str = 'ru') -> str:
        raise NotImplementedError

    async def prewarm(self) -> None:
        return None


class LocalWhisperProvider(SpeechToTextProvider):
    """CPU-optimised faster-whisper provider for Telegram audio.

    Long recordings are converted to 16 kHz mono chunks and decoded in parallel.
    Speed is deliberately prioritised over small quality gains from beam search.
    """

    _models: dict[tuple[str, str, str, int, int], object] = {}
    _lock = asyncio.Lock()

    def __init__(self, settings: Settings):
        self.settings = settings

    async def _get_model(self):
        cpu_threads = max(1, int(self.settings.whisper_cpu_threads or 1))
        workers = max(1, int(self.settings.whisper_num_workers or 1))
        key = (
            self.settings.whisper_model,
            self.settings.whisper_compute_type,
            self.settings.resolved_whisper_cache_dir,
            cpu_threads,
            workers,
        )
        async with self._lock:
            if key not in self.__class__._models:
                from faster_whisper import WhisperModel

                started = time.perf_counter()
                model = await asyncio.to_thread(
                    WhisperModel,
                    self.settings.whisper_model,
                    device='cpu',
                    compute_type=self.settings.whisper_compute_type,
                    download_root=self.settings.resolved_whisper_cache_dir,
                    cpu_threads=cpu_threads,
                    num_workers=workers,
                )
                self.__class__._models[key] = model
                logger.info(
                    'stt_model_ready model=%s compute=%s threads=%s workers=%s load_ms=%d',
                    self.settings.whisper_model,
                    self.settings.whisper_compute_type,
                    cpu_threads,
                    workers,
                    int((time.perf_counter() - started) * 1000),
                )
        return self.__class__._models[key]

    async def prewarm(self) -> None:
        await self._get_model()

    @staticmethod
    def _transcribe_sync(model, path: str, language: str) -> str:
        segments, _info = model.transcribe(
            path,
            language=language,
            vad_filter=True,
            vad_parameters={
                'min_silence_duration_ms': 350,
                'speech_pad_ms': 160,
            },
            beam_size=1,
            best_of=1,
            condition_on_previous_text=False,
            without_timestamps=True,
            word_timestamps=False,
        )
        return ' '.join(segment.text.strip() for segment in segments if segment.text.strip()).strip()

    @staticmethod
    def _duration_seconds(path: str) -> float:
        try:
            result = subprocess.run(
                [
                    'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1', path,
                ],
                capture_output=True,
                text=True,
                timeout=12,
                check=False,
            )
            return max(0.0, float((result.stdout or '0').strip() or 0))
        except Exception:
            return 0.0

    def _split_long_audio(self, path: str) -> tuple[str, list[str]]:
        temp_root = Path(self.settings.data_dir) / 'tmp'
        temp_root.mkdir(parents=True, exist_ok=True)
        folder = tempfile.mkdtemp(prefix='clarify-stt-', dir=temp_root)
        pattern = str(Path(folder) / 'chunk_%03d.wav')
        chunk_seconds = max(120, int(self.settings.whisper_chunk_seconds))
        command = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
            '-i', path,
            '-vn', '-ac', '1', '-ar', '16000',
            '-c:a', 'pcm_s16le',
            '-f', 'segment', '-segment_time', str(chunk_seconds), '-reset_timestamps', '1',
            pattern,
        ]
        try:
            subprocess.run(command, capture_output=True, timeout=45, check=True)
            chunks = sorted(str(item) for item in Path(folder).glob('chunk_*.wav'))
            if not chunks:
                raise RuntimeError('ffmpeg did not create STT chunks')
            return folder, chunks
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise

    async def transcribe(self, path: str, language: str = 'ru') -> str:
        started = time.perf_counter()
        model = await self._get_model()
        duration = await asyncio.to_thread(self._duration_seconds, path)
        threshold = max(120, int(self.settings.whisper_parallel_threshold_seconds))
        parallelism = max(1, int(self.settings.whisper_parallel_chunks))
        chunk_count = 1

        if duration < threshold or parallelism <= 1:
            text = await asyncio.to_thread(self._transcribe_sync, model, path, language)
            logger.info(
                'stt_done provider=local model=%s audio_seconds=%.1f chunks=1 elapsed_ms=%d',
                self.settings.whisper_model,
                duration,
                int((time.perf_counter() - started) * 1000),
            )
            return text

        split_started = time.perf_counter()
        try:
            folder, chunks = await asyncio.to_thread(self._split_long_audio, path)
        except Exception:
            text = await asyncio.to_thread(self._transcribe_sync, model, path, language)
            logger.info(
                'stt_done provider=local model=%s audio_seconds=%.1f chunks=1 split=fallback elapsed_ms=%d',
                self.settings.whisper_model,
                duration,
                int((time.perf_counter() - started) * 1000),
            )
            return text

        split_ms = int((time.perf_counter() - split_started) * 1000)
        chunk_count = len(chunks)
        semaphore = asyncio.Semaphore(min(parallelism, chunk_count))

        async def run_chunk(index: int, chunk: str):
            async with semaphore:
                text = await asyncio.to_thread(self._transcribe_sync, model, chunk, language)
                return index, text

        try:
            results = await asyncio.gather(*(run_chunk(i, chunk) for i, chunk in enumerate(chunks)))
            results.sort(key=lambda item: item[0])
            text = ' '.join(value for _index, value in results if value).strip()
            logger.info(
                'stt_done provider=local model=%s audio_seconds=%.1f chunks=%d parallel=%d split_ms=%d elapsed_ms=%d',
                self.settings.whisper_model,
                duration,
                chunk_count,
                min(parallelism, chunk_count),
                split_ms,
                int((time.perf_counter() - started) * 1000),
            )
            return text
        finally:
            await asyncio.to_thread(shutil.rmtree, folder, True)


class OpenAICompatibleSTTProvider(SpeechToTextProvider):
    def __init__(self, settings: Settings, client):
        self.settings = settings
        self.client = client

    async def transcribe(self, path: str, language: str = 'ru') -> str:
        if self.client is None:
            raise RuntimeError('AI client не настроен')
        started = time.perf_counter()

        async def request() -> str:
            with open(path, 'rb') as file:
                response = await self.client.audio.transcriptions.create(
                    model=self.settings.stt_remote_model,
                    file=file,
                    language=language,
                )
            return (response.text or '').strip()

        text = await asyncio.wait_for(request(), timeout=self.settings.stt_remote_timeout)
        logger.info(
            'stt_done provider=remote model=%s elapsed_ms=%d',
            self.settings.stt_remote_model,
            int((time.perf_counter() - started) * 1000),
        )
        return text


def build_stt(settings: Settings, ai_provider=None) -> SpeechToTextProvider:
    if settings.stt_provider.lower() in {'smartapi', 'openai', 'remote'}:
        return OpenAICompatibleSTTProvider(settings, getattr(ai_provider, 'client', None))
    return LocalWhisperProvider(settings)
