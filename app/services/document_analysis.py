from __future__ import annotations

import asyncio
import base64
import logging
import time

from app.processors.document_pipeline import (
    analyze_document_once,
    build_digest,
    extract_for_analysis,
    merge_pdf_ocr,
    render_pdf_page,
)
from app.services.core import plan_document_max_pages


logger = logging.getLogger(__name__)


async def _ocr_pages(ctx, path: str, page_numbers: list[int]) -> tuple[dict[int, str], dict[str, int]]:
    results: dict[int, str] = {}
    usage_total = {'input': 0, 'output': 0}
    concurrency = min(2, max(1, int(ctx.settings.document_ocr_concurrency)))
    semaphore = asyncio.Semaphore(concurrency)

    async def one(page_number: int):
        async with semaphore:
            png = await asyncio.to_thread(render_pdf_page, path, page_number, 120)
            async with ctx.ai_sem:
                raw, usage = await asyncio.wait_for(
                    ctx.ai.vision(
                        base64.b64encode(png).decode(),
                        'image/png',
                        (
                            f'Это страница {page_number} сканированного PDF. '
                            'Выполни точное OCR-распознавание текста. Сохрани числа, суммы, даты и таблицы. '
                            'Верни только распознанный текст без анализа.'
                        ),
                    ),
                    timeout=max(10.0, float(ctx.settings.document_ocr_page_timeout)),
                )
            text = (raw or '').strip()
            if text:
                results[page_number] = text
            usage_total['input'] += int(usage.get('input', 0) or 0)
            usage_total['output'] += int(usage.get('output', 0) or 0)

    outcomes = await asyncio.gather(*(one(page) for page in page_numbers), return_exceptions=True)
    failures = sum(isinstance(item, Exception) for item in outcomes)
    if failures:
        logger.warning('webapp_document_ocr_failures=%d pages=%d', failures, len(page_numbers))
    return results, usage_total


async def analyze_and_store_document(ctx, user, path: str, suffix: str, filename: str):
    """Fast document pipeline used by Mini App uploads.

    Text PDF/DOCX is locally extracted/indexed and always uses exactly one AI
    request for the initial analysis. Scanned PDF pages may require OCR vision
    calls, but OCR concurrency is bounded so they cannot occupy every AI slot.
    """
    started = time.perf_counter()
    max_pages = plan_document_max_pages(user, ctx.settings)
    async with ctx.doc_sem:
        extraction = await asyncio.to_thread(
            extract_for_analysis,
            path,
            suffix,
            max_pages,
            chars_per_page=ctx.settings.document_chars_per_page,
            max_text_chars=ctx.settings.document_max_text_chars,
        )

    ocr_requests = 0
    if extraction.scanned_pages:
        ocr_requests = len(extraction.scanned_pages)
        ocr_results, ocr_usage = await _ocr_pages(ctx, path, extraction.scanned_pages)
        extraction = merge_pdf_ocr(extraction, ocr_results)
        if ocr_results:
            await ctx.usage.record(user.id, ctx.settings.vision, 'webapp_pdf_vision_ocr', ocr_usage)

    text = (extraction.text or '').strip()
    if not text:
        raise ValueError('В документе не удалось найти текст')

    digest = build_digest(
        text,
        fast_path_chars=ctx.settings.document_fast_path_chars,
        max_chars=ctx.settings.document_digest_max_chars,
    )

    ai_started = time.perf_counter()
    try:
        async with ctx.ai_sem:
            result, usage, model = await analyze_document_once(
                ctx.ai,
                digest.text,
                f'{extraction.kind}-документ',
                model=ctx.settings.fast,
                timeout=ctx.settings.document_ai_timeout,
                max_tokens=min(ctx.settings.document_analysis_max_tokens, ctx.settings.openai_max_output_tokens),
            )
    except (asyncio.TimeoutError, TimeoutError):
        item = await ctx.materials.create(
            user.id,
            extraction.kind,
            filename,
            text,
            'Документ прочитан и сохранён. AI-анализ не успел ответить вовремя.',
        )
        logger.warning(
            'webapp_document_timeout type=%s chars=%d pages=%s estimated_pages=%s total_ms=%d',
            suffix.lstrip('.'),
            len(text),
            extraction.pages,
            extraction.estimated_pages,
            int((time.perf_counter() - started) * 1000),
        )
        return item

    ai_ms = int((time.perf_counter() - ai_started) * 1000)
    await ctx.usage.record(user.id, model, 'webapp_intake_document', usage)
    item = await ctx.materials.create(
        user.id,
        extraction.kind,
        result.title or filename,
        text,
        result.summary,
    )
    logger.info(
        'webapp_document_done type=%s chars=%d pages=%s estimated_pages=%s digest=%s selected_blocks=%d ai_ms=%d ai_requests=%d total_ms=%d model=%s',
        suffix.lstrip('.'),
        len(text),
        extraction.pages,
        extraction.estimated_pages,
        digest.used_digest,
        digest.selected_blocks,
        ai_ms,
        1 + ocr_requests,
        int((time.perf_counter() - started) * 1000),
        model,
    )
    return item
