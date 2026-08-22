from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from aiogram import F, Router
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.bot.razberi_helpers import ensure_quota, esc, get_user
from app.bot.razberi_keyboards import actions, pro_button
from app.processors.text import TextProcessor
from app.services.core import clarify_plan, plan_voice_max_seconds


async def _ffmpeg(*args: str) -> None:
    process = await asyncio.create_subprocess_exec(
        'ffmpeg',
        '-hide_banner',
        '-loglevel',
        'error',
        '-y',
        *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await process.communicate()
    if process.returncode != 0:
        message = stderr.decode('utf-8', errors='replace').strip()
        raise RuntimeError(message[-1200:] or f'ffmpeg exited with {process.returncode}')


async def _extract_audio(video_path: Path, audio_path: Path) -> None:
    """Prepare a compact mono track for Whisper instead of decoding the whole video."""
    await _ffmpeg(
        '-i', str(video_path),
        '-vn',
        '-ac', '1',
        '-ar', '16000',
        '-c:a', 'pcm_s16le',
        str(audio_path),
    )


async def _make_video_note(video_path: Path, output_path: Path) -> None:
    """Center-crop a normal video to Telegram's square video-note format."""
    await _ffmpeg(
        '-i', str(video_path),
        '-t', '60',
        '-vf', 'scale=512:512:force_original_aspect_ratio=increase,crop=512:512,setsar=1,fps=30',
        '-map', '0:v:0',
        '-map', '0:a:0?',
        '-c:v', 'libx264',
        '-preset', 'veryfast',
        '-crf', '25',
        '-pix_fmt', 'yuv420p',
        '-profile:v', 'main',
        '-level', '3.1',
        '-c:a', 'aac',
        '-b:a', '96k',
        '-movflags', '+faststart',
        str(output_path),
    )


async def _voice_like_count(ctx, user_id: int) -> int:
    total = 0
    for feature in ('voice', 'video', 'video_note'):
        total += await ctx.usage.feature_count_today(user_id, feature)
    return total


def _duration_text(duration: int) -> str:
    return f'{duration // 60:02d}:{duration % 60:02d}'


def _is_convert_only_material(material) -> bool:
    return bool(
        material
        and material.type == 'video'
        and (material.summary or '').startswith('Видео сохранено. Можно превратить его в Telegram-кружок.')
    )


def build_video_router(ctx) -> Router:
    router = Router(name='clarify-video')
    settings = ctx.settings

    @router.message(F.video | F.video_note)
    async def video_or_note(message: Message):
        user = await get_user(ctx, message.from_user)
        is_note = message.video_note is not None
        media = message.video_note or message.video
        if media is None:
            return

        duration = int(getattr(media, 'duration', 0) or 0)
        file_size = int(getattr(media, 'file_size', 0) or 0)
        media_type = 'video_note' if is_note else 'video'
        feature_name = 'video_note' if is_note else 'video'
        icon = '⭕' if is_note else '🎬'
        readable_name = 'кружок' if is_note else 'видео'

        if file_size > settings.max_file_size_mb * 1024 * 1024:
            return await message.answer(f'⚠️ {readable_name.capitalize()} больше {settings.max_file_size_mb} МБ.')

        cached = await ctx.materials.by_file_unique(user.id, getattr(media, 'file_unique_id', None))
        if cached and not _is_convert_only_material(cached):
            return await message.answer(
                '♻️ <b>Уже готово</b>\n\n' + esc(cached.summary or cached.title),
                reply_markup=actions(cached.id, cached.type),
            )

        max_seconds = plan_voice_max_seconds(user, settings)
        if max_seconds is not None and duration > max_seconds:
            if not is_note:
                material = cached or await ctx.materials.create(
                    user.id,
                    'video',
                    'Видео',
                    (message.caption or '').strip(),
                    'Видео сохранено. Можно превратить его в Telegram-кружок.',
                    getattr(media, 'file_id', None),
                    getattr(media, 'file_unique_id', None),
                )
                plan = clarify_plan(user, settings)
                return await message.answer(
                    f'{plan}: расшифровка видео до {max_seconds // 60} мин.\n\n⭕ Но сделать кружок можно без AI.',
                    reply_markup=actions(material.id, material.type),
                )
            plan = clarify_plan(user, settings)
            return await message.answer(
                f'{plan}: расшифровка кружков до {max_seconds // 60} мин. Более высокий лимит смотри в «Тарифах».',
                reply_markup=pro_button(),
            )

        if clarify_plan(user, settings) == 'FREE' and await _voice_like_count(ctx, user.id) >= settings.free_voice_daily_limit:
            if not is_note:
                material = cached or await ctx.materials.create(
                    user.id,
                    'video',
                    'Видео',
                    (message.caption or '').strip(),
                    'Видео сохранено. Можно превратить его в Telegram-кружок.',
                    getattr(media, 'file_id', None),
                    getattr(media, 'file_unique_id', None),
                )
                return await message.answer(
                    'Лимит расшифровок на сегодня закончился. ⭕ Конвертация в кружок всё равно доступна.',
                    reply_markup=actions(material.id, material.type),
                )
            return await message.answer('Лимит расшифровок на сегодня закончился. Открой «Тарифы».', reply_markup=pro_button())

        if not await ensure_quota(ctx, message, user):
            if not is_note:
                material = cached or await ctx.materials.create(
                    user.id,
                    'video',
                    'Видео',
                    (message.caption or '').strip(),
                    'Видео сохранено. Можно превратить его в Telegram-кружок.',
                    getattr(media, 'file_id', None),
                    getattr(media, 'file_unique_id', None),
                )
                await message.answer('⭕ Видео можно превратить в кружок без AI.', reply_markup=actions(material.id, material.type))
            return

        request_id = uuid.uuid4().hex
        video_path = Path(settings.data_dir, 'tmp', request_id + '.mp4')
        audio_path = Path(settings.data_dir, 'tmp', request_id + '.wav')
        progress = await message.answer(f'{icon} <b>Clarify обрабатывает {readable_name}…</b>\n1/2 · Расшифровываю речь')

        try:
            await ctx.bot.download(media, destination=video_path)
            try:
                await _extract_audio(video_path, audio_path)
            except RuntimeError:
                material = await ctx.materials.create(
                    user.id,
                    media_type,
                    'Кружок' if is_note else 'Видео',
                    (message.caption or '').strip(),
                    'В медиа нет доступной аудиодорожки.',
                    getattr(media, 'file_id', None),
                    getattr(media, 'file_unique_id', None),
                )
                return await progress.edit_text(
                    f'{icon} В {readable_name} нет доступной аудиодорожки.',
                    reply_markup=actions(material.id, material.type),
                )

            async with ctx.stt_sem:
                transcript = await ctx.stt.transcribe(str(audio_path), 'ru')

            if not transcript.strip():
                material = await ctx.materials.create(
                    user.id,
                    media_type,
                    'Кружок' if is_note else 'Видео',
                    (message.caption or '').strip(),
                    'Речь не обнаружена.',
                    getattr(media, 'file_id', None),
                    getattr(media, 'file_unique_id', None),
                )
                return await progress.edit_text(
                    f'{icon} Речь не обнаружена.',
                    reply_markup=actions(material.id, material.type),
                )

            await progress.edit_text(f'{icon} <b>Clarify обрабатывает {readable_name}…</b>\n2/2 · Выделяю смысл и действия')
            source_kind = 'кружок Telegram' if is_note else 'видео'
            source_text = transcript
            caption = (message.caption or '').strip()
            if caption and not is_note:
                source_text = f'Подпись к видео: {caption}\n\nРасшифровка:\n{transcript}'

            async with ctx.ai_sem:
                result, usage, model = await TextProcessor(ctx.ai).process(source_text, source_kind)
            await ctx.usage.record(user.id, model, feature_name, usage)
            material = await ctx.materials.create(
                user.id,
                media_type,
                result.title,
                transcript,
                result.summary,
                getattr(media, 'file_id', None),
                getattr(media, 'file_unique_id', None),
            )
            await ctx.metrics.inc('video_notes_processed' if is_note else 'videos_processed', user.id)
            await progress.edit_text(
                result.to_compact_telegram(f'{icon} <b>Clarify</b> · {_duration_text(duration)}'),
                reply_markup=actions(material.id, material.type),
            )
        except Exception as exc:
            await ctx.errors.record(request_id, message.from_user.id, feature_name, exc)
            await progress.edit_text(f'⚠️ Не получилось обработать {readable_name}. Попробуй отправить ещё раз.')
        finally:
            video_path.unlink(missing_ok=True)
            audio_path.unlink(missing_ok=True)

    @router.callback_query(F.data.startswith('circle:'))
    async def make_circle(call: CallbackQuery):
        await call.answer('Готовлю кружок…')
        if call.message is None:
            return
        try:
            material_id = int((call.data or '').split(':', 1)[1])
        except (TypeError, ValueError, IndexError):
            return await call.message.answer('⚠️ Не удалось определить видео.')

        user = await get_user(ctx, call.from_user)
        material = await ctx.materials.get(user.id, material_id)
        if material is None or material.type != 'video' or not material.telegram_file_id:
            return await call.message.answer('⚠️ Исходное видео больше недоступно. Отправь его боту ещё раз.')

        request_id = uuid.uuid4().hex
        source_path = Path(settings.data_dir, 'tmp', request_id + '.mp4')
        output_path = Path(settings.data_dir, 'tmp', request_id + '-circle.mp4')
        progress = await call.message.answer('⭕ <b>Делаю кружок…</b>\nОбрезаю по центру и подготавливаю для Telegram')

        try:
            await ctx.bot.download(material.telegram_file_id, destination=source_path)
            await _make_video_note(source_path, output_path)
            await ctx.bot.send_video_note(
                chat_id=call.message.chat.id,
                video_note=FSInputFile(output_path),
                length=512,
            )
            await ctx.metrics.inc('video_notes_created', user.id)
            await progress.edit_text('✅ Готово. Если исходное видео было длиннее минуты, в кружок вошли первые 60 секунд.')
        except Exception as exc:
            await ctx.errors.record(request_id, call.from_user.id, 'video_to_circle', exc)
            await progress.edit_text('⚠️ Не получилось сделать кружок. Попробуй другое MP4-видео или отправь его заново.')
        finally:
            source_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)

    return router
