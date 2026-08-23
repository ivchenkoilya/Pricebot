from __future__ import annotations

import asyncio
import base64
import logging
import mimetypes
import time
import uuid
from pathlib import Path

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import Message

from app.bot.razberi_helpers import ensure_quota, esc, get_user
from app.bot.razberi_keyboards import actions, pro_button
from app.processors.common import chunk_text, retrieve_chunks
from app.processors.document_pipeline import (
    analyze_document_once,
    build_digest,
    extract_for_analysis,
    merge_pdf_ocr,
    render_pdf_page,
)
from app.processors.documents import DocumentTooLarge
from app.services.core import plan_document_max_pages


logger = logging.getLogger(__name__)

DOCUMENT_EXTENSIONS = {'.pdf', '.docx', '.txt', '.md', '.xlsx', '.csv'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


def _page_label(extraction) -> str:
    value = extraction.display_pages
    return f' · {value}' if value else ''


def _cached_text(material) -> str:
    summary = esc(material.summary or material.title or 'Документ уже обработан.')
    return f'♻️ <b>Уже готово</b>\n\n{summary}'


def _question_context(text: str, question: str, settings) -> str:
    chunks = chunk_text(text)
    selected = retrieve_chunks(
        chunks,
        question,
        limit=max(3, int(settings.retrieval_chunk_limit)),
    )
    return '\n\n'.join(selected)[: int(settings.document_digest_max_chars)]


async def _ocr_missing_pdf_pages(ctx, progress, path: str, page_numbers: list[int], user_id: int):
    if not page_numbers:
        return {}, {'input': 0, 'output': 0}

    total = len(page_numbers)
    concurrency = min(2, max(1, int(ctx.settings.document_ocr_concurrency)))
    local_sem = asyncio.Semaphore(concurrency)
    progress_lock = asyncio.Lock()
    completed = 0
    results: dict[int, str] = {}
    usage_total = {'input': 0, 'output': 0}

    async def one(page_number: int):
        nonlocal completed
        async with local_sem:
            png = await asyncio.to_thread(render_pdf_page, path, page_number, 120)
            async with ctx.ai_sem:
                raw, usage = await asyncio.wait_for(
                    ctx.ai.vision(
                        base64.b64encode(png).decode(),
                        'image/png',
                        (
                            f'Это страница {page_number} сканированного PDF. '
                            'Выполни точное OCR-распознавание. Сохрани текст, числа, суммы, даты и структуру таблиц. '
                            'Верни только распознанный текст страницы без анализа и пояснений'
                        ),
                    ),
                    timeout=max(10.0, float(ctx.settings.document_ocr_page_timeout)),
                )
            results[page_number] = (raw or '').strip()
            usage_total['input'] += int(usage.get('input', 0) or 0)
            usage_total['output'] += int(usage.get('output', 0) or 0)
            async with progress_lock:
                completed += 1
                if completed == total or completed == 1 or completed % 5 == 0:
                    try:
                        await progress.edit_text(
                            f'👁 <b>Clarify распознаёт скан…</b>\n{completed}/{total} страниц'
                        )
                    except Exception:
                        pass

    tasks = [asyncio.create_task(one(page_number)) for page_number in page_numbers]
    outcomes = await asyncio.gather(*tasks, return_exceptions=True)
    failures = 0
    for page_number, outcome in zip(page_numbers, outcomes):
        if isinstance(outcome, Exception):
            failures += 1
            logger.warning('document_ocr_page_failed page=%s error=%s', page_number, outcome)
    if failures:
        await ctx.metrics.inc('document_ocr_page_failures', user_id, failures)
    return results, usage_total


def build_document_router(ctx) -> Router:
    router = Router(name='clarify-documents-v2')
    settings = ctx.settings

    @router.message(F.document)
    async def document(message: Message):
        document_item = message.document
        name = document_item.file_name or 'document'
        extension = Path(name).suffix.lower()
        if extension in IMAGE_EXTENSIONS:
            raise SkipHandler
        if extension not in DOCUMENT_EXTENSIONS:
            raise SkipHandler

        user = await get_user(ctx, message.from_user)
        caption = (message.caption or '').strip()
        if (document_item.file_size or 0) > settings.max_file_size_mb * 1024 * 1024:
            return await message.answer(f'⚠️ Файл больше {settings.max_file_size_mb} МБ.')

        mime = (document_item.mime_type or mimetypes.guess_type(name)[0] or 'application/octet-stream').lower()
        if mime in {'application/x-msdownload', 'application/x-executable', 'application/x-dosexec'}:
            return await message.answer('⚠️ Исполняемые файлы не принимаются.')

        cached = await ctx.materials.by_file_unique(user.id, document_item.file_unique_id)
        if cached and not caption:
            return await message.answer(
                _cached_text(cached),
                reply_markup=actions(cached.id, cached.type),
            )
        if not await ensure_quota(ctx, message, user):
            return

        request_id = uuid.uuid4().hex
        path = Path(settings.data_dir, 'tmp', request_id + extension)
        progress = await message.answer('📄 <b>Clarify читает файл…</b>\n1/2 · Извлекаю содержимое')
        started = time.perf_counter()
        download_ms = extract_ms = indexing_ms = ai_ms = 0
        ai_requests = 0
        extraction = None
        extracted_text = ''

        try:
            stage = time.perf_counter()
            await ctx.bot.download(document_item, destination=path)
            download_ms = int((time.perf_counter() - stage) * 1000)

            max_pages = plan_document_max_pages(user, settings)
            stage = time.perf_counter()
            async with ctx.doc_sem:
                extraction = await asyncio.to_thread(
                    extract_for_analysis,
                    str(path),
                    extension,
                    max_pages,
                    chars_per_page=settings.document_chars_per_page,
                    max_text_chars=settings.document_max_text_chars,
                )
            extract_ms = int((time.perf_counter() - stage) * 1000)

            if extraction.scanned_pages:
                await progress.edit_text(
                    f'👁 <b>Clarify распознаёт скан…</b>\n0/{len(extraction.scanned_pages)} страниц'
                )
                ocr_results, ocr_usage = await _ocr_missing_pdf_pages(
                    ctx,
                    progress,
                    str(path),
                    extraction.scanned_pages,
                    user.id,
                )
                if ocr_results:
                    extraction = merge_pdf_ocr(extraction, ocr_results)
                    await ctx.usage.record(user.id, settings.vision, 'pdf_vision_ocr', ocr_usage)

            extracted_text = (extraction.text or '').strip()
            if not extracted_text:
                return await progress.edit_text(
                    '⚠️ Не удалось извлечь текст из документа. Если это скан, попробуй более чёткий PDF.'
                )

            await ctx.metrics.inc('documents_extracted', user.id)
            page_text = _page_label(extraction)
            await progress.edit_text(
                f'📄 <b>Clarify читает файл…</b>{page_text}\n2/2 · Анализирую документ'
            )

            stage = time.perf_counter()
            if caption:
                context = _question_context(extracted_text, caption, settings)
                indexing_ms = int((time.perf_counter() - stage) * 1000)
                stage = time.perf_counter()
                ai_requests = 1
                async with ctx.ai_sem:
                    answer, usage = await asyncio.wait_for(
                        ctx.ai.ask(
                            caption + '\n\nОтветь прямо по документу. Не выдумывай. Для PDF указывай страницу, если рядом есть [Страница N].',
                            context,
                            model=settings.fast,
                        ),
                        timeout=max(5.0, float(settings.document_ai_timeout)),
                    )
                ai_ms = int((time.perf_counter() - stage) * 1000)
                await ctx.usage.record(user.id, settings.fast, 'document_caption', usage)
                material = await ctx.materials.create(
                    user.id,
                    extraction.kind,
                    name,
                    extracted_text,
                    answer[:4000],
                    document_item.file_id,
                    document_item.file_unique_id,
                )
                await ctx.metrics.inc('documents_processed', user.id)
                await progress.edit_text(
                    f'📄 <b>Clarify</b>{page_text}\n\n{esc(answer)}',
                    reply_markup=actions(material.id, material.type),
                )
            else:
                digest = build_digest(
                    extracted_text,
                    fast_path_chars=settings.document_fast_path_chars,
                    max_chars=settings.document_digest_max_chars,
                )
                indexing_ms = int((time.perf_counter() - stage) * 1000)
                stage = time.perf_counter()
                ai_requests = 1
                async with ctx.ai_sem:
                    result, usage, model = await analyze_document_once(
                        ctx.ai,
                        digest.text,
                        f'{extraction.kind}-документ',
                        model=settings.fast,
                        timeout=settings.document_ai_timeout,
                        max_tokens=min(settings.document_analysis_max_tokens, settings.openai_max_output_tokens),
                    )
                ai_ms = int((time.perf_counter() - stage) * 1000)
                await ctx.usage.record(user.id, model, 'document', usage)
                material = await ctx.materials.create(
                    user.id,
                    extraction.kind,
                    result.title or name,
                    extracted_text,
                    result.summary,
                    document_item.file_id,
                    document_item.file_unique_id,
                )
                await ctx.metrics.inc('documents_processed', user.id)
                prefix = f'📄 <b>Clarify</b> · документ{page_text}'
                await progress.edit_text(
                    result.to_telegram(prefix),
                    reply_markup=actions(material.id, material.type),
                )

        except DocumentTooLarge as exc:
            await progress.edit_text(
                f'⚠️ {esc(exc)}. Более высокий лимит доступен в «Тарифах».',
                reply_markup=pro_button(),
            )
        except (asyncio.TimeoutError, TimeoutError) as exc:
            await ctx.errors.record(request_id, message.from_user.id, 'document_ai_timeout', exc)
            if extracted_text and extraction is not None:
                material = await ctx.materials.create(
                    user.id,
                    extraction.kind,
                    name,
                    extracted_text,
                    'Документ прочитан и сохранён. AI-анализ не успел ответить вовремя.',
                    document_item.file_id,
                    document_item.file_unique_id,
                )
                await progress.edit_text(
                    f'📄 <b>Документ прочитан и сохранён</b>{_page_label(extraction)}\n\n'
                    'AI-анализ сейчас отвечает слишком долго. Текст не потерян — уже можно задавать вопросы по документу.',
                    reply_markup=actions(material.id, material.type),
                )
            else:
                await progress.edit_text('⚠️ Обработка документа превысила лимит времени. Попробуй ещё раз.')
        except Exception as exc:
            await ctx.errors.record(request_id, message.from_user.id, 'document', exc)
            if extracted_text and extraction is not None:
                material = await ctx.materials.create(
                    user.id,
                    extraction.kind,
                    name,
                    extracted_text,
                    'Документ прочитан и сохранён, но AI-анализ временно недоступен.',
                    document_item.file_id,
                    document_item.file_unique_id,
                )
                await progress.edit_text(
                    f'📄 <b>Документ прочитан и сохранён</b>{_page_label(extraction)}\n\n'
                    'AI-анализ сейчас недоступен. Текст сохранён — можешь задавать вопросы по документу.',
                    reply_markup=actions(material.id, material.type),
                )
            else:
                await progress.edit_text('⚠️ Не получилось обработать файл. Попробуй ещё раз или отправь его в другом формате.')
        finally:
            total_ms = int((time.perf_counter() - started) * 1000)
            logger.info(
                'document_done type=%s chars=%s pages=%s estimated_pages=%s download_ms=%d extract_ms=%d indexing_ms=%d ai_ms=%d ai_requests=%d total_ms=%d model=%s',
                extension.lstrip('.'),
                len(extracted_text),
                getattr(extraction, 'pages', None),
                getattr(extraction, 'estimated_pages', None),
                download_ms,
                extract_ms,
                indexing_ms,
                ai_ms,
                ai_requests,
                total_ms,
                settings.fast,
            )
            path.unlink(missing_ok=True)

    return router
