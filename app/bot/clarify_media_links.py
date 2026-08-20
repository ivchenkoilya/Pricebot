from __future__ import annotations

import asyncio
import uuid

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.ai.conversation import extract_urls, text_without_urls
from app.bot.razberi_helpers import ensure_quota, esc, get_user, send_long_text
from app.services.core import is_active_pro, is_creator
from app.services.media_downloader import MediaDownloadError, MediaInfo, is_media_url, media_intent


TRANSCRIPT_MARKER = '\n\nТранскрипт:\n'
_ACTIVE_MEDIA_JOBS: set[tuple[int, int]] = set()


def media_actions(material_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='⬇️ Скачать видео', callback_data=f'media:{material_id}:video'),
            InlineKeyboardButton(text='🎧 Скачать аудио', callback_data=f'media:{material_id}:audio'),
        ],
        [
            InlineKeyboardButton(text='📝 Расшифровать', callback_data=f'media:{material_id}:transcribe'),
            InlineKeyboardButton(text='✨ Краткий пересказ', callback_data=f'media:{material_id}:summary'),
        ],
        [
            InlineKeyboardButton(text='📌 Главное', callback_data=f'media:{material_id}:main'),
            InlineKeyboardButton(text='🧠 Объяснить', callback_data=f'media:{material_id}:plain'),
        ],
    ])


def _metadata_text(info: MediaInfo) -> str:
    size = f'{info.size_mb} МБ' if info.size_mb is not None else 'неизвестно заранее'
    return (
        f'Источник видео: {info.url}\n'
        f'Платформа: {info.platform}\n'
        f'Название: {info.title}\n'
        f'Автор: {info.author or "не указан"}\n'
        f'Длительность: {info.duration_text}\n'
        f'Размер: {size}'
    )


def _source_url(material) -> str:
    for line in (material.extracted_text or '').splitlines():
        if line.startswith('Источник видео: '):
            return line.split(': ', 1)[1].strip()
    return ''


def _info_card(info: MediaInfo) -> str:
    lines = [
        '🎬 <b>Нашёл видео</b>',
        '',
        f'<b>{esc(info.title)}</b>',
        f'📺 {esc(info.platform)}',
        f'⏱ {info.duration_text}',
    ]
    if info.author:
        lines.append(f'👤 {esc(info.author)}')
    if info.size_mb is not None:
        lines.append(f'💾 примерно {info.size_mb} МБ')
    lines += ['', '<b>Что сделать?</b>']
    return '\n'.join(lines)


def _plan_limits(user, settings) -> tuple[int, int | None]:
    creator = is_creator(user, settings)
    max_mb = settings.media_max_file_mb if (creator or is_active_pro(user)) else settings.media_free_max_file_mb
    max_minutes = None if creator else (
        settings.media_max_duration_minutes if is_active_pro(user) else settings.media_free_max_duration_minutes
    )
    return int(max_mb), max_minutes


async def _find_transcript_material(ctx, user_id: int, url: str):
    for material in await ctx.materials.latest(user_id, 20):
        text = material.extracted_text or ''
        if url in text and TRANSCRIPT_MARKER in text:
            return material
    return None


async def _ensure_transcript(ctx, user, material, progress: Message):
    url = _source_url(material)
    if not url:
        raise MediaDownloadError('Не удалось восстановить ссылку этого видео.')
    cached = await _find_transcript_material(ctx, user.id, url)
    if cached:
        return cached

    info = await ctx.media_downloader.inspect(url)
    _, max_minutes = _plan_limits(user, ctx.settings)
    if max_minutes is not None and info.duration > max_minutes * 60:
        raise MediaDownloadError(
            f'На твоём тарифе разбор видео доступен до {max_minutes} мин. Более длинные видео доступны в PRO.'
        )

    # Fast path: YouTube captions / auto-captions. This skips both media download
    # and local Whisper and is normally the difference between seconds and minutes.
    await progress.edit_text('⚡ <b>Ищу готовые субтитры…</b>')
    transcript = await ctx.media_downloader.fast_transcript(url)
    if transcript:
        stored = _metadata_text(info) + TRANSCRIPT_MARKER + transcript
        transcript_material = await ctx.materials.create(
            user.id,
            'video',
            info.title,
            stored,
            f'Транскрипт видео готов · {info.platform} · {info.duration_text}',
        )
        await ctx.metrics.inc('media_transcribed_from_subtitles', user.id)
        return transcript_material

    await progress.edit_text('🎧 <b>Субтитров нет — получаю аудио…</b>')
    audio_path = None
    try:
        audio_path = await ctx.media_downloader.download_audio(url, max_mb=ctx.settings.media_max_file_mb)
        await progress.edit_text('🎤 <b>Распознаю речь…</b>')
        async with ctx.stt_sem:
            transcript = await ctx.stt.transcribe(str(audio_path), 'ru')
        transcript = (transcript or '').strip()
        if not transcript:
            raise MediaDownloadError('Не удалось обнаружить речь в этом видео.')
        stored = _metadata_text(info) + TRANSCRIPT_MARKER + transcript
        transcript_material = await ctx.materials.create(
            user.id,
            'video',
            info.title,
            stored,
            f'Транскрипт видео готов · {info.platform} · {info.duration_text}',
        )
        await ctx.metrics.inc('media_transcribed', user.id)
        return transcript_material
    finally:
        ctx.media_downloader.cleanup(audio_path)


def build_media_links_router(ctx) -> Router:
    router = Router(name='clarify-media-links')
    settings = ctx.settings

    async def inspect_and_create(message: Message, url: str):
        progress = await message.answer('🎬 <b>Проверяю видео…</b>')
        try:
            info = await ctx.media_downloader.inspect(url)
            user = await get_user(ctx, message.from_user)
            material = await ctx.materials.create(
                user.id,
                'video_link',
                info.title,
                _metadata_text(info),
                f'{info.platform} · {info.duration_text}',
            )
            await ctx.metrics.inc('media_links_opened', material.user_id)
            await progress.edit_text(_info_card(info), reply_markup=media_actions(material.id))
            # Warm the cheapest path in the background while the user is deciding
            # which button to press. Only public caption metadata is prefetched.
            ctx.media_downloader.prefetch_transcript(info.url)
            return material, progress
        except MediaDownloadError as exc:
            await progress.edit_text(f'⚠️ {esc(str(exc))}')
            return None, progress

    async def run_action(message: Message, user, material, action: str, progress: Message | None = None):
        url = _source_url(material)
        if not url:
            return await message.answer('⚠️ Не удалось восстановить ссылку видео. Пришли её ещё раз.')
        max_mb, max_minutes = _plan_limits(user, settings)
        try:
            info = await ctx.media_downloader.inspect(url)
            if max_minutes is not None and info.duration > max_minutes * 60 and action in {'video', 'audio', 'transcribe', 'summary', 'main', 'plain'}:
                return await message.answer(
                    f'⚠️ На твоём тарифе видео доступно до {max_minutes} мин. Для более длинных роликов нужен PRO.'
                )

            if action == 'video':
                status = progress or await message.answer('⬇️ <b>Загружаю видео…</b>')
                path = None
                try:
                    await status.edit_text('⬇️ <b>Загружаю видео…</b>\nЦель — уложиться примерно в 30 секунд.')
                    path = await ctx.media_downloader.download_video(url, max_mb=max_mb, max_height=settings.media_video_max_height)
                    filename = ctx.media_downloader.safe_filename(info.title, path.suffix or '.mp4')
                    caption = f'✅ <b>{esc(info.title)}</b>\n📺 {esc(info.platform)} · ⏱ {info.duration_text}'
                    try:
                        await message.answer_video(FSInputFile(path, filename=filename), caption=caption, supports_streaming=True)
                    except Exception:
                        await message.answer_document(FSInputFile(path, filename=filename), caption=caption)
                    await status.edit_text('✅ Видео отправлено.')
                    await ctx.metrics.inc('media_video_downloaded', user.id)
                finally:
                    ctx.media_downloader.cleanup(path)
                return

            if action == 'audio':
                status = progress or await message.answer('🎧 <b>Получаю аудиодорожку…</b>')
                path = None
                try:
                    path = await ctx.media_downloader.download_audio(url, max_mb=max_mb)
                    filename = ctx.media_downloader.safe_filename(info.title, '.mp3')
                    caption = f'✅ <b>{esc(info.title)}</b>\n🎧 {esc(info.platform)} · ⏱ {info.duration_text}'
                    try:
                        await message.answer_audio(FSInputFile(path, filename=filename), caption=caption, title=info.title, performer=info.author or None)
                    except Exception:
                        await message.answer_document(FSInputFile(path, filename=filename), caption=caption)
                    await status.edit_text('✅ Аудио отправлено.')
                    await ctx.metrics.inc('media_audio_downloaded', user.id)
                finally:
                    ctx.media_downloader.cleanup(path)
                return

            status = progress or await message.answer('🎤 <b>Готовлю расшифровку…</b>')
            transcript_material = await _ensure_transcript(ctx, user, material, status)
            transcript = (transcript_material.extracted_text or '').split(TRANSCRIPT_MARKER, 1)[-1].strip()

            if action == 'transcribe':
                await status.edit_text('✅ <b>Расшифровка готова.</b>\n\nТекст отправляю следующим сообщением.')
                await send_long_text(message, transcript)
                return

            if not await ensure_quota(ctx, message, user):
                return
            prompts = {
                'summary': 'Кратко перескажи содержание видео в 3–7 предложениях. Сначала дай основную мысль, затем главный вывод.',
                'main': 'Выдели только самые важные мысли видео краткими пунктами. Отдельно укажи важные даты, суммы и инструкции, если они есть.',
                'plain': 'Объясни содержание этого видео простыми словами человеку без специальных знаний. Не выдумывай факты.',
            }
            prompt = prompts.get(action)
            if not prompt:
                return await status.edit_text('⚠️ Неизвестное действие.')
            await status.edit_text('✨ <b>Разбираю содержание…</b>')
            context = await ctx.materials.context(user.id, transcript_material.id, prompt)
            async with ctx.ai_sem:
                answer, usage = await ctx.ai.ask(prompt, context, model=settings.fast)
            await ctx.usage.record(user.id, settings.fast, f'media_{action}', usage)
            await status.edit_text(esc(answer), reply_markup=media_actions(material.id))
        except MediaDownloadError as exc:
            target = progress or message
            if target is message:
                await message.answer(f'⚠️ {esc(str(exc))}')
            else:
                await target.edit_text(f'⚠️ {esc(str(exc))}')
        except Exception as exc:
            request_id = uuid.uuid4().hex
            await ctx.errors.record(request_id, message.chat.id if message.chat else None, 'media_link', exc)
            target = progress or message
            text = '⚠️ Не получилось обработать видео. Возможно, платформа временно ограничила сервер.'
            if target is message:
                await message.answer(text)
            else:
                await target.edit_text(text)

    async def run_with_deadline(message: Message, user, material, action: str, progress: Message):
        key = (user.id, material.id)
        if key in _ACTIVE_MEDIA_JOBS:
            await progress.edit_text('⚡ Это видео уже обрабатывается. Дождись текущего действия — повторно запускать его не нужно.')
            return
        _ACTIVE_MEDIA_JOBS.add(key)
        try:
            await asyncio.wait_for(
                run_action(message, user, material, action, progress),
                timeout=max(5, int(settings.media_action_timeout_seconds)),
            )
        except TimeoutError:
            await progress.edit_text(
                '⏱ <b>Остановил ожидание через 30 секунд.</b>\n\n'
                'Clarify не будет висеть минутами. Для анализа попробуй «Расшифровать» или «Краткий пересказ» — '
                'если у ролика есть субтитры, они обычно работают значительно быстрее.'
            )
        finally:
            _ACTIVE_MEDIA_JOBS.discard(key)

    @router.message(F.text)
    async def media_link(message: Message):
        value = (message.text or '').strip()
        urls = extract_urls(value)
        media_url = next((url for url in urls if is_media_url(url)), None)
        if not media_url:
            raise SkipHandler
        if not settings.media_download_enabled:
            return await message.answer('🎬 Работа с видео-ссылками сейчас отключена в настройках Clarify.')

        instruction = text_without_urls(value)
        action = media_intent(instruction)
        material, progress = await inspect_and_create(message, media_url)
        if not material:
            return
        if action == 'inspect':
            return
        user = await get_user(ctx, message.from_user)
        await run_with_deadline(message, user, material, action, progress)

    @router.callback_query(F.data.startswith('media:'))
    async def media_callback(callback: CallbackQuery):
        try:
            _, material_raw, action = callback.data.split(':', 2)
            material_id = int(material_raw)
        except (ValueError, AttributeError):
            return await callback.answer('Некорректное действие', show_alert=True)
        user = await get_user(ctx, callback.from_user)
        material = await ctx.materials.get(user.id, material_id)
        if not material:
            return await callback.answer('Видео больше не найдено в материалах', show_alert=True)
        key = (user.id, material.id)
        if key in _ACTIVE_MEDIA_JOBS:
            return await callback.answer('Уже обрабатываю это видео ⚡', show_alert=False)
        await callback.answer()
        progress = await callback.message.answer('⚡ <b>Готовлю…</b>')
        await run_with_deadline(callback.message, user, material, action, progress)

    return router
