from __future__ import annotations

import asyncio
import base64
import io
import mimetypes
import uuid
from pathlib import Path

from aiogram import F, Router
from aiogram.types import Message
from PIL import Image

from app.bot.razberi_helpers import ensure_quota, esc, get_user
from app.bot.razberi_keyboards import actions, pro_button
from app.processors.documents import DocumentTooLarge, extract_document, render_pdf_pages
from app.processors.text import TextProcessor
from app.services.core import is_active_pro


def _optimized_image_payload(path: Path, settings) -> tuple[str, str]:
    """Resize screenshots before vision. Less transfer + fewer vision tokens."""
    with Image.open(path) as image:
        image.load()
        image.thumbnail((settings.image_max_side, settings.image_max_side), Image.Resampling.LANCZOS)
        if image.mode != 'RGB':
            image = image.convert('RGB')
        output = io.BytesIO()
        image.save(output, format='JPEG', quality=settings.image_jpeg_quality, optimize=True)
    return base64.b64encode(output.getvalue()).decode(), 'image/jpeg'


def _material_text_from_result(result, raw: str = '') -> str:
    parts = []
    if getattr(result, 'source_text', ''):
        parts.append(result.source_text)
    if result.summary:
        parts.append('Кратко: ' + result.summary)
    if result.key_points:
        parts.append('Главное:\n' + '\n'.join('- ' + item for item in result.key_points))
    if result.tasks:
        parts.append('Задачи:\n' + '\n'.join('- ' + item for item in result.tasks))
    if result.dates:
        parts.append('Даты: ' + '; '.join(result.dates))
    if result.amounts:
        parts.append('Суммы: ' + '; '.join(result.amounts))
    if result.warnings:
        parts.append('Важно:\n' + '\n'.join('- ' + item for item in result.warnings))
    return '\n\n'.join(parts).strip() or raw


def build_media_router(ctx) -> Router:
    router = Router(name='clarify-media')
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
                '♻️ <b>Уже готово</b>\n\n' + esc(cached.summary or cached.title),
                reply_markup=actions(cached.id, cached.type),
            )

        if not is_active_pro(user):
            if duration > settings.free_voice_max_seconds:
                return await message.answer(
                    f'FREE: голосовое до {settings.free_voice_max_seconds // 60} мин. Для длинных — PRO.',
                    reply_markup=pro_button(),
                )
            if await ctx.usage.feature_count_today(user.id, 'voice') >= settings.free_voice_daily_limit:
                return await message.answer('Лимит голосовых на сегодня закончился.', reply_markup=pro_button())
        if not await ensure_quota(ctx, message, user):
            return

        progress = await message.answer('🎤 <b>Clarify слушает…</b>\n1/2 · Расшифровываю речь')
        request_id = uuid.uuid4().hex
        if message.voice:
            extension = '.ogg'
        else:
            extension = Path(getattr(message.audio, 'file_name', '') or '.mp3').suffix.lower() or '.mp3'
        if extension not in {'.mp3', '.wav', '.m4a', '.ogg', '.opus', '.aac', '.flac'}:
            extension = '.audio'
        path = Path(settings.data_dir, 'tmp', request_id + extension)

        try:
            await ctx.bot.download(media, destination=path)
            async with ctx.stt_sem:
                transcript = await ctx.stt.transcribe(str(path), 'ru')
            if not transcript.strip():
                return await progress.edit_text('⚠️ Речь не обнаружена.')

            await progress.edit_text('🎤 <b>Clarify слушает…</b>\n2/2 · Выделяю смысл и действия')
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
                result.to_telegram(
                    f'🎤 <b>Clarify</b> · голосовое {duration // 60:02d}:{duration % 60:02d}'
                ),
                reply_markup=actions(material.id, material.type),
            )
        except Exception as exc:
            await ctx.errors.record(request_id, message.from_user.id, 'voice', exc)
            await progress.edit_text('⚠️ Не получилось обработать голосовое. Попробуй ещё раз или отправь аудиофайл.')
        finally:
            path.unlink(missing_ok=True)

    @router.message(F.photo)
    async def photo(message: Message):
        user = await get_user(ctx, message.from_user)
        if not await ensure_quota(ctx, message, user):
            return
        photo_item = message.photo[-1]
        cached = await ctx.materials.by_file_unique(user.id, photo_item.file_unique_id)
        if cached:
            return await message.answer(
                '♻️ <b>Уже готово</b>\n\n' + esc(cached.summary or cached.title),
                reply_markup=actions(cached.id, cached.type),
            )
        path = Path(settings.data_dir, 'tmp', uuid.uuid4().hex + '.jpg')
        progress = await message.answer('📸 <b>Clarify смотрит…</b>\nЧитаю скриншот и сразу выделяю главное')
        try:
            await ctx.bot.download(photo_item, destination=path)
            image_b64, image_mime = await asyncio.to_thread(_optimized_image_payload, path, settings)
            async with ctx.ai_sem:
                result, vision_usage, model, raw = await ctx.ai.analyze_image(
                    image_b64,
                    image_mime,
                    'Разбери изображение или скриншот',
                )
            await ctx.usage.record(user.id, model, 'image', vision_usage)
            material_text = _material_text_from_result(result, raw)
            material = await ctx.materials.create(
                user.id, 'image', result.title, material_text, result.summary, photo_item.file_id, photo_item.file_unique_id
            )
            await ctx.metrics.inc('images_processed', user.id)
            await progress.edit_text(
                result.to_telegram('📸 <b>Clarify</b> · изображение разобрано'),
                reply_markup=actions(material.id, material.type),
            )
        except Exception as exc:
            await ctx.errors.record(uuid.uuid4().hex, message.from_user.id, 'image', exc)
            await progress.edit_text(
                '⚠️ Не получилось разобрать изображение. Возможно, выбранная AI-модель не поддерживает vision.'
            )
        finally:
            path.unlink(missing_ok=True)

    @router.message(F.document)
    async def document(message: Message):
        user = await get_user(ctx, message.from_user)
        document_item = message.document
        name = document_item.file_name or 'document'
        extension = Path(name).suffix.lower()
        document_extensions = {'.pdf', '.docx', '.txt', '.md', '.xlsx', '.csv'}
        image_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
        if extension not in document_extensions | image_extensions:
            return await message.answer('⚠️ Формат пока не поддерживается. Можно PDF, DOCX, TXT, MD, XLSX, CSV, JPG, PNG, WEBP.')
        if (document_item.file_size or 0) > settings.max_file_size_mb * 1024 * 1024:
            return await message.answer(f'⚠️ Файл больше {settings.max_file_size_mb} МБ.')
        mime = (document_item.mime_type or mimetypes.guess_type(name)[0] or 'application/octet-stream').lower()
        if mime in {'application/x-msdownload', 'application/x-executable', 'application/x-dosexec'}:
            return await message.answer('⚠️ Исполняемые файлы не принимаются.')

        cached = await ctx.materials.by_file_unique(user.id, document_item.file_unique_id)
        if cached:
            return await message.answer(
                '♻️ <b>Уже готово</b>\n\n' + esc(cached.summary or cached.title),
                reply_markup=actions(cached.id, cached.type),
            )
        if not await ensure_quota(ctx, message, user):
            return

        path = Path(settings.data_dir, 'tmp', uuid.uuid4().hex + extension)
        progress = await message.answer('📄 <b>Clarify читает файл…</b>\n1/2 · Извлекаю текст локально')
        try:
            await ctx.bot.download(document_item, destination=path)
            if extension in image_extensions:
                image_b64, image_mime = await asyncio.to_thread(_optimized_image_payload, path, settings)
                async with ctx.ai_sem:
                    result, usage, model, raw = await ctx.ai.analyze_image(
                        image_b64,
                        image_mime,
                        'Разбери изображение или скриншот',
                    )
                await ctx.usage.record(user.id, model, 'image', usage)
                material = await ctx.materials.create(
                    user.id, 'image', result.title or name, _material_text_from_result(result, raw), result.summary,
                    document_item.file_id, document_item.file_unique_id,
                )
                await ctx.metrics.inc('images_processed', user.id)
                return await progress.edit_text(
                    result.to_telegram('📸 <b>Clarify</b> · изображение разобрано'),
                    reply_markup=actions(material.id, material.type),
                )

            max_pages = settings.pro_document_max_pages if is_active_pro(user) else settings.free_document_max_pages
            async with ctx.doc_sem:
                text, pages, kind = await asyncio.to_thread(extract_document, str(path), extension, max_pages)

            if not text.strip() and extension == '.pdf':
                await progress.edit_text('👁 <b>Clarify распознаёт скан…</b>\nСтраницы обрабатываются параллельно')
                images = await asyncio.to_thread(render_pdf_pages, str(path), max_pages)

                async def ocr_page(page_number: int, png: bytes):
                    async with ctx.ai_sem:
                        raw, usage = await ctx.ai.vision(
                            base64.b64encode(png).decode(),
                            'image/png',
                            f'Это скан PDF, страница {page_number}. Выполни точное OCR-распознавание текста; сохрани таблицы, суммы и даты. Верни только распознанное содержимое страницы',
                        )
                    return page_number, raw, usage

                scanned = await asyncio.gather(*(ocr_page(page_number, png) for page_number, png in images))
                scanned.sort(key=lambda item: item[0])
                text = '\n\n'.join(f'[Страница {page_number}]\n{raw}' for page_number, raw, _ in scanned)
                if text.strip():
                    total_usage = {
                        'input': sum(item[2].get('input', 0) for item in scanned),
                        'output': sum(item[2].get('output', 0) for item in scanned),
                    }
                    await ctx.usage.record(user.id, settings.vision, 'pdf_vision_ocr', total_usage)

            if not text.strip():
                return await progress.edit_text(
                    '⚠️ В документе почти нет извлекаемого текста. Если это скан, выбранная AI-модель должна поддерживать vision.'
                )

            await progress.edit_text('📄 <b>Clarify читает файл…</b>\n2/2 · Собираю главное, сроки и риски')
            async with ctx.ai_sem:
                result, usage, model = await TextProcessor(ctx.ai).process(text, kind)
            await ctx.usage.record(user.id, model, 'document', usage)
            material = await ctx.materials.create(
                user.id, kind, result.title or name, text, result.summary,
                document_item.file_id, document_item.file_unique_id,
            )
            await ctx.metrics.inc('documents_processed', user.id)
            page_text = f' · {pages} стр.' if pages else ''
            await progress.edit_text(
                result.to_telegram(f'📄 <b>Clarify</b> · документ{page_text}'),
                reply_markup=actions(material.id, material.type),
            )
        except DocumentTooLarge as exc:
            await progress.edit_text(f'⚠️ {esc(exc)}. Для больших документов нужен PRO.', reply_markup=pro_button())
        except Exception as exc:
            await ctx.errors.record(uuid.uuid4().hex, message.from_user.id, 'document', exc)
            if extension in image_extensions:
                await progress.edit_text('⚠️ Не получилось разобрать изображение. Возможно, выбранная AI-модель не поддерживает vision.')
            else:
                await progress.edit_text('⚠️ Не получилось обработать файл. Попробуй ещё раз или отправь его в другом формате.')
        finally:
            path.unlink(missing_ok=True)

    return router
