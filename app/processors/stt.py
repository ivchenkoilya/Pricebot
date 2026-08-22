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
    """Adaptive faster-whisper provider for Clarify.

    Accuracy is deliberately prioritised for short Telegram voice notes, video
    notes and short videos: those use the multilingual ``small`` model with a
    wider beam. Long recordings still switch to the lightweight model configured
    in settings so a 10–60 minute file does not pin a small Amvera CPU forever.
    """

    _models: dict[tuple[str, str, str, int, int], object] = {}
    _lock = asyncio.Lock()

    def __init__(self, settings: Settings):
        self.settings = settings

    @staticmethod
    def _cgroup_cpu_limit() -> int | None:
        try:
            raw = Path('/sys/fs/cgroup/cpu.max').read_text(encoding='utf-8').strip().split()
            if len(raw) >= 2 and raw[0] != 'max':
                quota = int(raw[0])
                period = int(raw[1])
                if quota > 0 and period > 0:
                    return max(1, (quota + period - 1) // period)
        except (OSError, ValueError):
            pass
        return None

    def _runtime_cpu_config(self) -> tuple[int, int]:
        requested_threads = max(1, int(self.settings.whisper_cpu_threads or 1))
        requested_workers = max(1, int(self.settings.whisper_num_workers or 1))
        cpu_limit = self._cgroup_cpu_limit()
        if cpu_limit is None:
            return requested_threads, requested_workers

        workers = min(requested_workers, cpu_limit)
        threads = min(requested_threads, max(1, cpu_limit // workers))
        return threads, workers

    async def _get_model(self, model_name: str | None = None):
        cpu_threads, workers = self._runtime_cpu_config()
        model_name = (model_name or self.settings.resolved_whisper_model).strip()
        key = (
            model_name,
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
                    model_name,
                    device='cpu',
                    compute_type=self.settings.whisper_compute_type,
                    download_root=self.settings.resolved_whisper_cache_dir,
                    cpu_threads=cpu_threads,
                    num_workers=workers,
                )
                self.__class__._models[key] = model
                logger.info(
                    'stt_model_ready model=%s configured_model=%s compute=%s threads=%s workers=%s load_ms=%d',
                    model_name,
                    self.settings.whisper_model,
                    self.settings.whisper_compute_type,
                    cpu_threads,
                    workers,
                    int((time.perf_counter() - started) * 1000),
                )
        return self.__class__._models[key]

    async def prewarm(self) -> None:
        # Most real Telegram messages are short. Warm the accuracy model first so
        # the first user does not wait for it to load after deployment.
        await self._get_model('small')

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

    def _prepare_audio(self, path: str) -> tuple[str | None, str | None]:
        """Make speech easier to hear without touching the user's source file.

        Telegram/video audio can be quiet, boomy or noisy. A small high/low-pass
        plus dynamic normalisation usually helps Whisper on phone recordings and
        factory/background noise. If ffmpeg rejects the filter we simply fall
        back to the original input.
        """
        temp_root = Path(self.settings.data_dir) / 'tmp'
        temp_root.mkdir(parents=True, exist_ok=True)
        folder = tempfile.mkdtemp(prefix='clarify-stt-clean-', dir=temp_root)
        output = str(Path(folder) / 'speech.wav')
        command = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
            '-i', path,
            '-vn', '-ac', '1', '-ar', '16000',
            '-af', 'highpass=f=70,lowpass=f=7800,dynaudnorm=f=200:g=7:p=0.95',
            '-c:a', 'pcm_s16le',
            output,
        ]
        try:
            subprocess.run(command, capture_output=True, timeout=30, check=True)
            if Path(output).exists() and Path(output).stat().st_size > 1000:
                return folder, output
        except Exception:
            pass
        shutil.rmtree(folder, ignore_errors=True)
        return None, None

    def _split_long_audio(self, path: str) -> tuple[str, list[str]]:
        temp_root = Path(self.settings.data_dir) / 'tmp'
        temp_root.mkdir(parents=True, exist_ok=True)
        folder = tempfile.mkdtemp(prefix='clarify-stt-', dir=temp_root)
        pattern = str(Path(folder) / 'chunk_%03d.wav')
        chunk_seconds = min(120, max(60, int(self.settings.whisper_chunk_seconds)))
        command = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
            '-i', path,
            '-vn', '-ac', '1', '-ar', '16000',
            '-af', 'highpass=f=70,lowpass=f=7800,dynaudnorm=f=200:g=7:p=0.95',
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

    def _model_for_duration(self, duration: float) -> str:
        long_after = max(60, int(self.settings.whisper_long_model_after_seconds))
        fast_model = (self.settings.whisper_long_model or '').strip()
        if fast_model and duration >= long_after:
            return fast_model
        # ``small`` is a large step up from base/tiny on short colloquial Russian,
        # especially when the clip contains slang or background noise.
        return 'small'

    @staticmethod
    def _decode_profile(duration: float, model_name: str, long_model: str) -> tuple[int, bool, bool]:
        is_long_model = bool(long_model and model_name == long_model)
        if is_long_model:
            return 1, False, True
        if duration <= 45:
            # Short messages are cheap enough to decode carefully. Disabling VAD
            # here also avoids clipping a single short phrase such as "чёрт возьми".
            return 5, True, False
        if duration <= 180:
            return 3, True, True
        return 2, False, True

    @staticmethod
    def _transcribe_sync(
        model,
        path: str,
        language: str,
        beam_size: int,
        condition_on_previous_text: bool,
        vad_filter: bool,
    ) -> tuple[str, float]:
        initial_prompt = None
        if language.lower().startswith('ru'):
            initial_prompt = (
                'Точная дословная расшифровка русской разговорной речи. '
                'Сохраняй обычные русские слова, имена, числа, сленг и междометия. '
                'Не выдумывай необычные слова, если слышна нормальная русская фраза.'
            )

        kwargs = dict(
            language=language,
            vad_filter=vad_filter,
            beam_size=max(1, beam_size),
            best_of=1,
            temperature=0.0,
            condition_on_previous_text=condition_on_previous_text,
            initial_prompt=initial_prompt,
            without_timestamps=True,
            word_timestamps=False,
        )
        if vad_filter:
            kwargs['vad_parameters'] = {
                'min_silence_duration_ms': 500,
                'speech_pad_ms': 300,
            }

        segments, _info = model.transcribe(path, **kwargs)
        pieces: list[str] = []
        scores: list[float] = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                pieces.append(text)
                try:
                    scores.append(float(segment.avg_logprob))
                except (TypeError, ValueError, AttributeError):
                    pass
        score = sum(scores) / len(scores) if scores else -99.0
        return ' '.join(pieces).strip(), score

    async def transcribe(self, path: str, language: str = 'ru') -> str:
        started = time.perf_counter()
        duration = await asyncio.to_thread(self._duration_seconds, path)
        model_name = self._model_for_duration(duration)
        model = await self._get_model(model_name)
        long_model = (self.settings.whisper_long_model or '').strip()
        beam_size, condition_previous, vad_filter = self._decode_profile(duration, model_name, long_model)

        threshold = min(120, max(60, int(self.settings.whisper_parallel_threshold_seconds)))
        _threads, model_workers = self._runtime_cpu_config()
        parallelism = min(
            max(1, int(self.settings.whisper_parallel_chunks)),
            max(1, model_workers),
        )

        # Short messages get one cleaned pass. If Whisper itself reports very low
        # confidence, retry the untouched source and keep whichever pass is more
        # confident. This costs extra CPU only on doubtful short clips.
        if duration < threshold or parallelism <= 1:
            clean_folder = None
            clean_path = None
            if duration <= 180:
                clean_folder, clean_path = await asyncio.to_thread(self._prepare_audio, path)
            input_path = clean_path or path
            try:
                text, score = await asyncio.to_thread(
                    self._transcribe_sync,
                    model,
                    input_path,
                    language,
                    beam_size,
                    condition_previous,
                    vad_filter,
                )
                if duration <= 45 and clean_path and score < -0.85:
                    raw_text, raw_score = await asyncio.to_thread(
                        self._transcribe_sync,
                        model,
                        path,
                        language,
                        max(5, beam_size),
                        True,
                        False,
                    )
                    if raw_text and raw_score > score:
                        text, score = raw_text, raw_score
                logger.info(
                    'stt_done provider=local model=%s beam=%s confidence=%.3f audio_seconds=%.1f chunks=1 elapsed_ms=%d',
                    model_name,
                    beam_size,
                    score,
                    duration,
                    int((time.perf_counter() - started) * 1000),
                )
                return text
            finally:
                if clean_folder:
                    await asyncio.to_thread(shutil.rmtree, clean_folder, True)

        split_started = time.perf_counter()
        try:
            folder, chunks = await asyncio.to_thread(self._split_long_audio, path)
        except Exception:
            text, _score = await asyncio.to_thread(
                self._transcribe_sync,
                model,
                path,
                language,
                beam_size,
                condition_previous,
                vad_filter,
            )
            logger.info(
                'stt_done provider=local model=%s beam=%s audio_seconds=%.1f chunks=1 split=fallback elapsed_ms=%d',
                model_name,
                beam_size,
                duration,
                int((time.perf_counter() - started) * 1000),
            )
            return text

        split_ms = int((time.perf_counter() - split_started) * 1000)
        chunk_count = len(chunks)
        semaphore = asyncio.Semaphore(min(parallelism, chunk_count))

        async def run_chunk(index: int, chunk: str):
            async with semaphore:
                text, _score = await asyncio.to_thread(
                    self._transcribe_sync,
                    model,
                    chunk,
                    language,
                    beam_size,
                    condition_previous,
                    True,
                )
                return index, text

        try:
            results = await asyncio.gather(*(run_chunk(i, chunk) for i, chunk in enumerate(chunks)))
            results.sort(key=lambda item: item[0])
            text = ' '.join(value for _index, value in results if value).strip()
            logger.info(
                'stt_done provider=local model=%s beam=%s audio_seconds=%.1f chunks=%d parallel=%d split_ms=%d elapsed_ms=%d',
                model_name,
                beam_size,
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
