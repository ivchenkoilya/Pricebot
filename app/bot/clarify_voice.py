from __future__ import annotations

import html
import uuid
from pathlib import Path

from aiogram import F, Router
from aiogram.types import Message

from app.bot.razberi_helpers import ensure_quota, get_user
from app.bot.razberi_keyboards import actions, pro_button
from app.processors.text import TextProcessor
from app.services.core import clarify_plan, plan_voice_max_seconds


TELEGRAM_SAFE_LIMIT = 3900


def _short(value: str, limit: int) -> str:
    value = ' '.join((value or '').strip().split())
    if len(value) <= limit:
        return value
    return value[: max(1, limit - 1)].rstrip() + '…'


def _transcript_preview(transcript: str, limit: int = 1400) -> str:
    transcript = (transcript or '').strip()
    if len(transcript) <= limit:
        return transcript
    return transcript[: max(1, limit - 80)].rstrip() + '…\n\nПолная расшифровка сохранена в «Исходник».'


def _analysis_text(result) -> str:
    parts: list[str] = []
    summary = getattr(result, 'summary', '') or ''
    if summary:
        parts.append(html.escape(_short(summary, 850)))

    key_points = list(getattr(result, 'key_points', []) or [])[:3]
    if key_points:
        parts.append('<b>Главное</b>\n' + '\n'.join(f'• {html.escape(_short(item, 220))}' for item in key_points))

    tasks = list(getattr(result, 'tasks', []) or [])[:2]
    if tasks:
        parts.append('<b>Что сделать</b>\n' + '\n'.join(f'☐ {html.escape(_short(item, 220))}' for item in tasks))

    warnings = list(getattr(result, 'warnings', []) or [])[:1]
    if warnings:
        parts.append('⚠️ ' + html.escape(_short(warnings[0], 220)))

    if not parts:
        title = getattr(result, 'title', '') or 'Содержательного вывода нет.'
        parts.append(html.escape(_short(title, 850)))

    return '\n\n'.join(parts)


def _voice_card(transcript: str, result, duration: int) -> str:
    minutes, seconds = divmod(max(0, int(duration or 0)), 60)
    analysis = _analysis_text(result)
    preview = html.escape(_transcript_preview(transcript, 1400))
    text = (
        f'🎤 <b>Clarify</b> · {minutes:02d}:{seconds:02d}\n\n'
        f'📝 <b>Расшифровка</b>\n{preview}\n\n'
        f'🧠 <b>Что понял Clarify</b>\n{analysis}'
    )
    if len(text) <= TELEGRAM_SAFE_LIMIT:
        return text

    # Keep the analysis visible and shrink only the transcript preview.
    fixed = (
        f'🎤 <b>Clarify</b> · {minutes:02d}:{seconds:02d}\n\n'
        f'📝 <b>Расшифровка</b>\n\n\n'
        f'🧠 <b>Что понял Clarify</b>\n{analysis}'
    )
    available = max(240, TELEGRAM_SAFE_LIMIT - len(fixed) - 120)
    # HTML escaping can expand the text, so use a conservative raw-character cap.
    raw_limit = max(220, min(900, available // 2))
    preview = html.escape(_transcript_preview(transcript, raw_limit))
    return (
        f'🎤 <b>Clarify</b> · {minutes:02d}:{seconds:02d}\n\n'
        f'📝 <b>Расшифровка</b>\n{preview}\n\n'
        f'🧠 <b>Что понял Clarify</b>\n{analysis}'
    )


def _cached_voice_card(material, duration: int) -> str:
    minutes, seconds = divmod(max(0, int(duration or 0)), 60)
    transcript = html.escape(_transcript_preview(getattr(material, 'extracted_text', '') or '', 1500))
    summary = html.escape(_short(getattr(material, 'summary', '') or 'Материал уже обработан.', 1000))
    return (
        f'♻️ <b>Уже готово</b> · {minutes:02d}:{seconds:02d}\n\n'
        f'📝 <b>Расшифровка</b>\n{transcript}\n\n'
        f'🧠 <b>Что понял Clarify</b>\n{summary}'
    )


async def _transcribe_voice(ctx, path: str) -> str:
    """Use SpeechKit language auto-detection when Yandex is the primary STT.

    Clarify users often mix Russian and English in one Telegram voice note.
    SpeechKit v3 supports language_code=['auto']; the current provider already
    forwards the language argument into that field. Local Whisper keeps the
    explicit Russian hint because its adapter expects a concrete language code.
    """
    provider = (ctx.settings.stt_provider or 'local').strip().lower()
    language = 'auto' if provider == 'yandex' else 'ru'
    try:
        return await ctx.stt.transcribe(path, language)
    except Exception:
        # If Yandex is unavailable and its local fallback rejects the special
        # "auto" code, retry through the ordinary Russian-safe path.
        if language != 'ru':
            return await ctx.stt.transcribe(path, 'ru')
        raise


def build_voice_router(ctx) -> Router:
    router = Router(name='clarify-voice-v2')
    settings = ctx.settings

    @router.message(F.voice | F.audio)
    async def audio(message: Message):
        user = await get_user(ctx, message.from_user)
        media = message.voice or message.audio
        duration = int(getattr(media, 'duration', 0) or 0)

        if int(getattr(media, 'file_size', 0) or 0) > settings.max_file_size_mb * 1024 * 1024:
            return await message.answer(f'⚠️ Аудиофайл больше {settings.max_file_size_mb} МБ.')

        cached = await ctx.materials.by_file_unique(user.id, getattr(media, 'file_unique_id', None))
        if cached:
            return await message.answer(
                _cached_voice_card(cached, duration),
                reply_markup=actions(cached.id, cached.type),
            )

        max_seconds = plan_voice_max_seconds(user, settings)
        if max_seconds is not None and duration > max_seconds:
            plan = clarify_plan(user, settings)
            return await message.answer(
                f'{plan}: голосовые до {max_seconds // 60} мин. Более высокий лимит смотри в «Тарифах».',
                reply_markup=pro_button(),
            )

        if clarify_plan(user, settings) == 'FREE' and await ctx.usage.feature_count_today(user.id, 'voice') >= settings.free_voice_daily_limit:
            return await message.answer(
                'Лимит голосовых на сегодня закончился. Открой «Тарифы».',
                reply_markup=pro_button(),
            )
        if not await ensure_quota(ctx, message, user):
            return

        progress = await message.answer('🎤 <b>Clarify слушает…</b>\n1/2 · Расшифровываю речь')
        request_id = uuid.uuid4().hex
        extension = '.ogg' if message.voice else (Path(getattr(message.audio, 'file_name', '') or '.mp3').suffix.lower() or '.mp3')
        if extension not in {'.mp3', '.wav', '.m4a', '.ogg', '.opus', '.aac', '.flac'}:
            extension = '.audio'
        path = Path(settings.data_dir, 'tmp', request_id + extension)
        transcript = ''

        try:
            await ctx.bot.download(media, destination=path)
            async with ctx.stt_sem:
                transcript = await _transcribe_voice(ctx, str(path))
            transcript = transcript.strip()
            if not transcript:
                return await progress.edit_text('⚠️ Речь не обнаружена.')

            live_preview = html.escape(_transcript_preview(transcript, 1500))
            await progress.edit_text(
                '🎤 <b>Clarify слушает…</b>\n2/2 · Анализирую смысл\n\n'
                f'📝 <b>Расшифровка</b>\n{live_preview}'
            )

            async with ctx.ai_sem:
                result, usage, model = await TextProcessor(ctx.ai).process(transcript, 'голосовое')
            await ctx.usage.record(user.id, model, 'voice', usage)

            material = await ctx.materials.create(
                user.id,
                'voice',
                result.title,
                transcript,
                result.summary,
                getattr(media, 'file_id', None),
                getattr(media, 'file_unique_id', None),
            )
            await ctx.metrics.inc('voice_processed', user.id)
            await progress.edit_text(
                _voice_card(transcript, result, duration),
                reply_markup=actions(material.id, material.type),
            )
        except Exception as exc:
            await ctx.errors.record(request_id, message.from_user.id, 'voice', exc)
            if transcript:
                preview = html.escape(_transcript_preview(transcript, 2200))
                await progress.edit_text(
                    f'📝 <b>Расшифровка</b>\n{preview}\n\n'
                    '⚠️ Расшифровка готова, но Clarify не смог завершить AI-анализ. Попробуй ещё раз.'
                )
            else:
                await progress.edit_text('⚠️ Не получилось обработать голосовое. Попробуй ещё раз или отправь аудиофайл.')
        finally:
            path.unlink(missing_ok=True)

    return router
