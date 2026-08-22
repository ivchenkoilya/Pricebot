from __future__ import annotations

import asyncio
import base64
import json
import logging
import shutil
import tempfile
import time
from pathlib import Path

import httpx

from app.config.settings import Settings


logger = logging.getLogger(__name__)


class YandexSpeechKitProvider:
    """Yandex SpeechKit v3 asynchronous STT with optional local fallback.

    The Kazakhstan Yandex Cloud region exposes SpeechKit STT through API v3.
    Clarify converts Telegram/video audio to compact mono OGG Opus and sends it
    directly in the request body. This keeps a one-hour recording comfortably
    below the API v3 60 MB request-body limit in normal conditions.
    """

    def __init__(self, settings: Settings, fallback=None):
        self.settings = settings
        self.fallback = fallback

    async def prewarm(self) -> None:
        # Cloud STT needs no model warm-up. Keep the local fallback lazy so a
        # Yandex-backed deployment does not spend RAM/CPU loading Whisper.
        return None

    @property
    def _headers(self) -> dict[str, str]:
        return {
            'Authorization': f'Api-Key {self.settings.yandex_speechkit_api_key.strip()}',
            'x-folder-id': self.settings.yandex_speechkit_folder_id.strip(),
            'Content-Type': 'application/json',
        }

    @property
    def _base_url(self) -> str:
        return self.settings.yandex_speechkit_endpoint.rstrip('/')

    def _prepare_ogg(self, path: str) -> tuple[str, str]:
        temp_root = Path(self.settings.data_dir) / 'tmp'
        temp_root.mkdir(parents=True, exist_ok=True)
        folder = tempfile.mkdtemp(prefix='clarify-yandex-stt-', dir=temp_root)
        output = str(Path(folder) / 'speech.ogg')

        # SpeechKit v3 accepts OGG_OPUS. 64 kbps mono is transparent enough for
        # speech recognition while keeping long Telegram recordings compact.
        import subprocess

        command = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
            '-i', path,
            '-vn', '-ac', '1', '-ar', '48000',
            '-af', 'highpass=f=70,lowpass=f=7800,dynaudnorm=f=200:g=7:p=0.95',
            '-c:a', 'libopus', '-b:a', '64k', '-vbr', 'on',
            output,
        ]
        try:
            subprocess.run(command, capture_output=True, timeout=90, check=True)
            if not Path(output).exists() or Path(output).stat().st_size < 100:
                raise RuntimeError('ffmpeg produced an empty OGG file')
            return folder, output
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise

    @staticmethod
    def _extract_text_items(raw: str) -> list[dict]:
        raw = (raw or '').strip()
        if not raw:
            return []
        try:
            value = json.loads(raw)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                return [value]
        except json.JSONDecodeError:
            pass

        # Some SpeechKit gateway responses are newline-delimited JSON messages.
        items: list[dict] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                items.append(value)
        return items

    @staticmethod
    def _best_transcript(messages: list[dict]) -> str:
        finals: dict[int, str] = {}
        refinements: dict[int, str] = {}
        fallback_finals: list[str] = []

        for message in messages:
            final = message.get('final') or {}
            alternatives = final.get('alternatives') or []
            if alternatives and isinstance(alternatives[0], dict):
                text = str(alternatives[0].get('text') or '').strip()
                if text:
                    try:
                        index = int((message.get('audioCursors') or {}).get('finalIndex') or len(finals))
                    except (TypeError, ValueError):
                        index = len(finals)
                    finals[index] = text
                    fallback_finals.append(text)

            refinement = message.get('finalRefinement') or {}
            normalized = refinement.get('normalizedText') or {}
            alternatives = normalized.get('alternatives') or []
            if alternatives and isinstance(alternatives[0], dict):
                text = str(alternatives[0].get('text') or '').strip()
                if text:
                    try:
                        index = int(refinement.get('finalIndex') or 0)
                    except (TypeError, ValueError):
                        index = 0
                    refinements[index] = text

        if refinements or finals:
            indexes = sorted(set(finals) | set(refinements))
            parts = [refinements.get(index) or finals.get(index) or '' for index in indexes]
            text = ' '.join(part for part in parts if part).strip()
            if text:
                return text
        return ' '.join(fallback_finals).strip()

    async def _recognize_yandex(self, path: str, language: str) -> str:
        if not self.settings.yandex_speechkit_api_key.strip():
            raise RuntimeError('YANDEX_SPEECHKIT_API_KEY не задан')
        if not self.settings.yandex_speechkit_folder_id.strip():
            raise RuntimeError('YANDEX_SPEECHKIT_FOLDER_ID не задан')

        folder = None
        started = time.perf_counter()
        try:
            folder, ogg_path = await asyncio.to_thread(self._prepare_ogg, path)
            encoded = await asyncio.to_thread(
                lambda: base64.b64encode(Path(ogg_path).read_bytes()).decode('ascii')
            )
            lang = 'ru-RU' if language.lower().startswith('ru') else language
            payload = {
                'content': encoded,
                'recognitionModel': {
                    'model': self.settings.yandex_speechkit_model,
                    'audioFormat': {
                        'containerAudio': {'containerAudioType': 'OGG_OPUS'},
                    },
                    'textNormalization': {
                        'textNormalization': 'TEXT_NORMALIZATION_ENABLED',
                        'profanityFilter': False,
                        'literatureText': False,
                        'phoneFormattingMode': 'PHONE_FORMATTING_MODE_DISABLED',
                    },
                    'languageRestriction': {
                        'restrictionType': 'WHITELIST',
                        'languageCode': [lang],
                    },
                },
            }

            timeout = httpx.Timeout(
                connect=20.0,
                read=max(60.0, float(self.settings.yandex_speechkit_timeout)),
                write=max(60.0, float(self.settings.yandex_speechkit_timeout)),
                pool=20.0,
            )
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f'{self._base_url}/stt/v3/recognizeFileAsync',
                    headers=self._headers,
                    json=payload,
                )
                response.raise_for_status()
                operation = response.json()
                operation_id = str(operation.get('id') or '').strip()
                if not operation_id:
                    raise RuntimeError(f'SpeechKit не вернул operation id: {response.text[:500]}')

                deadline = time.monotonic() + max(30.0, float(self.settings.yandex_speechkit_timeout))
                poll_interval = max(0.5, float(self.settings.yandex_speechkit_poll_interval))
                while True:
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Yandex SpeechKit слишком долго обрабатывает аудио')
                    status_response = await client.get(
                        f'{self._base_url}/operations/{operation_id}',
                        headers=self._headers,
                    )
                    status_response.raise_for_status()
                    status = status_response.json()
                    if status.get('done'):
                        if status.get('error'):
                            error = status.get('error') or {}
                            raise RuntimeError(error.get('message') or 'Yandex SpeechKit вернул ошибку')
                        break
                    await asyncio.sleep(poll_interval)

                result_response = await client.get(
                    f'{self._base_url}/stt/v3/getRecognition',
                    headers=self._headers,
                    params={'operationId': operation_id},
                )
                result_response.raise_for_status()
                messages = self._extract_text_items(result_response.text)
                text = self._best_transcript(messages)
                if not text:
                    raise RuntimeError('Yandex SpeechKit не обнаружил распознаваемую речь')

            logger.info(
                'stt_done provider=yandex model=%s elapsed_ms=%d',
                self.settings.yandex_speechkit_model,
                int((time.perf_counter() - started) * 1000),
            )
            return text
        finally:
            if folder:
                await asyncio.to_thread(shutil.rmtree, folder, True)

    async def transcribe(self, path: str, language: str = 'ru') -> str:
        try:
            return await self._recognize_yandex(path, language)
        except Exception as exc:
            logger.warning('Yandex SpeechKit failed, fallback=%s: %s', bool(self.fallback), exc)
            if self.fallback is None or not self.settings.yandex_speechkit_fallback_local:
                raise
            return await self.fallback.transcribe(path, language)
