from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.config.settings import Settings


class SpeechToTextProvider:
    async def transcribe(self, path: str, language: str = 'ru') -> str:
        raise NotImplementedError

    async def prewarm(self) -> None:
        return None


class LocalWhisperProvider(SpeechToTextProvider):
    """CPU-optimised faster-whisper provider.

    Long recordings are converted to lightweight 16 kHz mono chunks and decoded
    in parallel.  This matters on Amvera much more than beam-search quality: a
    10–20 minute voice should not spend many minutes in one serial Whisper call.
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
        model = await self._get_model()
        duration = await asyncio.to_thread(self._duration_seconds, path)
        threshold = max(120, int(self.settings.whisper_parallel_threshold_seconds))
        parallelism = max(1, int(self.settings.whisper_parallel_chunks))

        # Short voice notes are faster without an ffmpeg split. Long recordings
        # benefit strongly from two simultaneous tiny-model workers.
        if duration < threshold or parallelism <= 1:
            return await asyncio.to_thread(self._transcribe_sync, model, path, language)

        try:
            folder, chunks = await asyncio.to_thread(self._split_long_audio, path)
        except Exception:
            return await asyncio.to_thread(self._transcribe_sync, model, path, language)

        semaphore = asyncio.Semaphore(min(parallelism, len(chunks)))

        async def run_chunk(index: int, chunk: str):
            async with semaphore:
                text = await asyncio.to_thread(self._transcribe_sync, model, chunk, language)
                return index, text

        try:
            results = await asyncio.gather(*(run_chunk(i, chunk) for i, chunk in enumerate(chunks)))
            results.sort(key=lambda item: item[0])
            return ' '.join(text for _index, text in results if text).strip()
        finally:
            await asyncio.to_thread(shutil.rmtree, folder, True)


class OpenAICompatibleSTTProvider(SpeechToTextProvider):
    def __init__(self, settings: Settings, client):
        self.settings = settings
        self.client = client

    async def transcribe(self, path: str, language: str = 'ru') -> str:
        if self.client is None:
            raise RuntimeError('AI client не настроен')

        async def request() -> str:
            with open(path, 'rb') as file:
                response = await self.client.audio.transcriptions.create(
                    model=self.settings.stt_remote_model,
                    file=file,
                    language=language,
                )
            return (response.text or '').strip()

        return await asyncio.wait_for(request(), timeout=self.settings.stt_remote_timeout)


def build_stt(settings: Settings, ai_provider=None) -> SpeechToTextProvider:
    if settings.stt_provider.lower() in {'smartapi', 'openai', 'remote'}:
        return OpenAICompatibleSTTProvider(settings, getattr(ai_provider, 'client', None))
    return LocalWhisperProvider(settings)
