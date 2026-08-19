from __future__ import annotations

import asyncio

from app.config.settings import Settings


class SpeechToTextProvider:
    async def transcribe(self, path: str, language: str = 'ru') -> str:
        raise NotImplementedError


class LocalWhisperProvider(SpeechToTextProvider):
    _models: dict[tuple[str, str, str], object] = {}
    _lock = asyncio.Lock()

    def __init__(self, settings: Settings):
        self.settings = settings

    async def _get_model(self):
        key = (
            self.settings.whisper_model,
            self.settings.whisper_compute_type,
            self.settings.resolved_whisper_cache_dir,
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
                    cpu_threads=0,
                )
                self.__class__._models[key] = model
        return self.__class__._models[key]

    async def transcribe(self, path: str, language: str = 'ru') -> str:
        model = await self._get_model()

        def run() -> str:
            segments, _info = model.transcribe(
                path,
                language=language,
                vad_filter=True,
                beam_size=1,
                best_of=1,
                condition_on_previous_text=False,
                without_timestamps=True,
            )
            return ' '.join(segment.text.strip() for segment in segments if segment.text.strip()).strip()

        return await asyncio.to_thread(run)


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
