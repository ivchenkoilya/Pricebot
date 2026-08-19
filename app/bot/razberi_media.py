from __future__ import annotations

import asyncio
import base64
import mimetypes
import uuid
from pathlib import Path

from aiogram import F, Router
from aiogram.types import Message

from app.bot.razberi_helpers import ensure_quota, esc, get_user
from app.bot.razberi_keyboards import actions, pro_button
from app.processors.documents import DocumentTooLarge, extract_document, render_pdf_pages
from app.processors.text import TextProcessor
from app.services.core import is_active_pro


def build_media_router(ctx) -> Router:
    router = Router(name='razberi-media')
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
                '♻️ <b>Этот файл уже разобран</b>\n\n' + esc(cached.summary or cached.title),
                reply_markup=actions(cached.id),
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

        progress = await message.answer('🎤 Скачиваю голосовое…')
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
            await progress.edit_text('🎤 Расшифровываю…')
            async with ctx.stt_sem:
                transcript = await ctx.stt.transcribe(str(path), 'ru')
            if not transcript.strip():
                return await progress.edit_text('⚠️ Речь не обнаружена.')

            await progress.edit_text('🧠 Выделяю главное…')
            async with ctx.ai_sem:
                result, usage, model = await TextProcessor(ctx.ai).process(transcript)
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
                    f'🎤 <b>Голосовое разобрано</b>\n⏱ Длительность: {duration // 60:02d}:{duration % 60:02d}'
                ),
                reply_markup=actions(material.id),
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
                '♻️ <b>Это изображение уже разобрано</b>\n\n' + esc(cached.summary or cached.title),
                reply_markup=actions(cached.id),
            )
        path = Path(settings.data_dir, 'tmp', uuid.uuid4().hex + '.jpg')
        progress = await message.answer('📸 Разбираю изображение…')
        try:
            await ctx.bot.download(photo_item, destination=path)
            raw, vision_usage = await ctx.ai.vision(
                base64.b64encode(path.read_bytes()).decode(),
                'image/jpeg',
                'Разбери изображение/скриншот',
            )
            await ctx.usage.record(user.id, settings.vision, 'image', vision_usage)
            result, analysis_usage, model = await ctx.ai.analyze_text(raw, 'описание изображения')
            await ctx.usage.record(user.id, model, 'image_analysis', analysis_usage)
            material = await ctx.materials.create(
                user.id, 'image', result.title, raw, result.summary, photo_item.file_id, photo_item.file_unique_id
            )
            await ctx.metrics.inc('images_processed', user.id)
            await progress.edit_text(
                result.to_telegram('📸 <b>Изображение разобрано</b>'),
                reply_markup=actions(material.id),
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
                '♻️ <b>Этот файл уже разобран</b>\n\n' + esc(cached.summary or cached.title),
                reply_markup=actions(cached.id),
            )
        if not await ensure_quota(ctx, message, user):
            return

        path = Path(settings.data_dir, 'tmp', uuid.uuid4().hex + extension)
        progress = await message.answer('📄 Скачиваю файл…')
        try:
            await ctx.bot.download(document_item, destination=path)
            if extension in image_extensions:
                await progress.edit_text('📸 Разбираю изображение…')
                raw, vision_usage = await ctx.ai.vision(
                    base64.b64encode(path.read_bytes()).decode(),
                    mime if mime.startswith('image/') else 'image/jpeg',
                    'Разбери изображение/скриншот',
                )
                await ctx.usage.record(user.id, settings.vision, 'image', vision_usage)
                result, analysis_usage, model = await ctx.ai.analyze_text(raw, 'описание изображения')
                await ctx.usage.record(user.id, model, 'image_analysis', analysis_usage)
                material = await ctx.materials.create(
                    user.id, 'image', result.title or name, raw, result.summary,
                    document_item.file_id, document_item.file_unique_id,
                )
                await ctx.metrics.inc('images_processed', user.id)
                return await progress.edit_text(
                    result.to_telegram('📸 <b>Изображение разобрано</b>'), reply_markup=actions(material.id)
                )

            await progress.edit_text('📄 Извлекаю структуру и текст…')
            max_pages = settings.pro_document_max_pages if is_active_pro(user) else settings.free_document_max_pages
            async with ctx.doc_sem:
                text, pages, kind = await asyncio.to_thread(extract_document, str(path), extension, max_pages)

            if not text.strip() and extension == '.pdf':
                await progress.edit_text('👁 В PDF нет text layer. Пробую распознать сканированные страницы через vision…')
                images = await asyncio.to_thread(render_pdf_pages, str(path), max_pages)
                ocr_parts: list[str] = []
                total_usage = {'input': 0, 'output': 0}
                for page_number, png in images:
                    async with ctx.ai_sem:
                        raw, usage = await ctx.ai.vision(
                            base64.b64encode(png).decode(),
                            'image/png',
                            f'Это скан PDF, страница {page_number}. Выполни точное OCR-распознавание текста; сохрани таблицы, суммы и даты. Верни только распознанное содержимое страницы',
                        )
                    ocr_parts.append(f'[Страница {page_number}]\n{raw}')
                    total_usage['input'] += usage.get('input', 0)
                    total_usage['output'] += usage.get('output', 0)
                text = '\n\n'.join(ocr_parts)
                if text.strip():
                    await ctx.usage.record(user.id, settings.vision, 'pdf_vision_ocr', total_usage)

            if not text.strip():
                return await progress.edit_text(
                    '⚠️ В документе почти нет извлекаемого текста. Если это скан, выбранная AI-модель должна поддерживать vision.'
                )

            await progress.edit_text('🧠 Выделяю главное…')
            async with ctx.ai_sem:
                result, usage, model = await TextProcessor(ctx.ai).process(text, kind)
            await ctx.usage.record(user.id, model, 'document', usage)
            material = await ctx.materials.create(
                user.id, kind, result.title or name, text, result.summary,
                document_item.file_id, document_item.file_unique_id,
            )
            await ctx.metrics.inc('documents_processed', user.id)
            page_text = f'\n{pages} страниц' if pages else ''
            await progress.edit_text(
                result.to_telegram(f'📄 <b>Документ разобран</b>{page_text}'),
                reply_markup=actions(material.id),
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
