from __future__ import annotations

import asyncio
import math
import re
from dataclasses import dataclass
from pathlib import Path

import fitz

from app.processors.documents import DocumentTooLarge, extract_document


IMPORTANT_TERMS = {
    'обязан': 8,
    'обязанность': 8,
    'должен': 7,
    'необходимо': 6,
    'требуется': 6,
    'срок': 8,
    'дата': 5,
    'не позднее': 8,
    'оплата': 8,
    'стоимость': 7,
    'цена': 6,
    'сумма': 7,
    'штраф': 9,
    'неустой': 9,
    'пеня': 9,
    'ответствен': 8,
    'риск': 7,
    'гарант': 7,
    'постав': 6,
    'достав': 6,
    'расторж': 8,
    'приемк': 5,
    'приёмк': 5,
    'требован': 6,
}

DATE_RE = re.compile(r'\b(?:\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?|\d{4}-\d{2}-\d{2})\b')
MONEY_RE = re.compile(r'\b\d[\d\s\u00a0\u2009\u202f]*(?:[.,]\d{1,2})?\s*(?:₽|руб(?:лей|ля|ль|\.)?|USD|EUR|доллар|евро)\b', re.I)
PERCENT_RE = re.compile(r'\b\d+(?:[.,]\d+)?\s*%')
PAGE_RE = re.compile(r'^\[Страница\s+(\d+)\]\s*$', re.I | re.M)
HEADING_RE = re.compile(r'^(?:\d+(?:\.\d+)*[.)]?\s+)?[А-ЯA-ZЁ][^.!?]{2,110}$')


@dataclass(slots=True)
class DocumentExtraction:
    text: str
    kind: str
    pages: int | None
    estimated_pages: int | None
    scanned_pages: list[int]
    page_texts: dict[int, str]

    @property
    def display_pages(self) -> str:
        if self.pages is not None:
            return f'{self.pages} стр.'
        if self.estimated_pages is not None:
            return f'≈{self.estimated_pages} стр.'
        return ''


@dataclass(slots=True)
class DocumentDigest:
    text: str
    source_chars: int
    selected_blocks: int
    used_digest: bool


def estimate_pages(text: str, chars_per_page: int = 2500) -> int:
    chars_per_page = max(500, int(chars_per_page or 2500))
    compact = re.sub(r'\s+', ' ', text or '').strip()
    if not compact:
        return 0
    return max(1, math.ceil(len(compact) / chars_per_page))


def _pdf_extraction(path: str, max_pages: int, min_text_chars_per_page: int = 24) -> DocumentExtraction:
    doc = fitz.open(path)
    try:
        pages = len(doc)
        if pages > max_pages:
            raise DocumentTooLarge(f'PDF: {pages} стр., лимит {max_pages}')

        page_texts: dict[int, str] = {}
        scanned: list[int] = []
        for index, page in enumerate(doc, 1):
            text = page.get_text('text').strip()
            useful_chars = len(re.sub(r'\s+', '', text))
            if useful_chars >= min_text_chars_per_page:
                page_texts[index] = text
            else:
                scanned.append(index)

        joined = '\n\n'.join(
            f'[Страница {number}]\n{text}' for number, text in sorted(page_texts.items()) if text
        )
        return DocumentExtraction(
            text=joined,
            kind='pdf',
            pages=pages,
            estimated_pages=pages,
            scanned_pages=scanned,
            page_texts=page_texts,
        )
    finally:
        doc.close()


def extract_for_analysis(
    path: str,
    extension: str,
    max_pages: int,
    *,
    chars_per_page: int = 2500,
    max_text_chars: int = 1_500_000,
) -> DocumentExtraction:
    ext = extension.lower()
    if ext == '.pdf':
        result = _pdf_extraction(path, max_pages)
    else:
        text, pages, kind = extract_document(path, ext, max_pages)
        estimated = pages if pages is not None else estimate_pages(text, chars_per_page)
        if ext == '.docx' and estimated > max_pages:
            raise DocumentTooLarge(
                f'DOCX: примерно {estimated} стр., лимит тарифа {max_pages}'
            )
        result = DocumentExtraction(
            text=text,
            kind=kind,
            pages=pages,
            estimated_pages=estimated or None,
            scanned_pages=[],
            page_texts={},
        )

    if len(result.text) > max(50_000, int(max_text_chars)):
        approx = result.estimated_pages or estimate_pages(result.text, chars_per_page)
        raise DocumentTooLarge(
            f'Документ содержит слишком много текста ({len(result.text):,} символов, примерно {approx} стр.)'
            .replace(',', ' ')
        )
    return result


def render_pdf_page(path: str, page_number: int, dpi: int = 120) -> bytes:
    doc = fitz.open(path)
    try:
        if page_number < 1 or page_number > len(doc):
            raise ValueError(f'Страница {page_number} вне диапазона PDF')
        page = doc[page_number - 1]
        matrix = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        return pix.tobytes('png')
    finally:
        doc.close()


def merge_pdf_ocr(extraction: DocumentExtraction, ocr_pages: dict[int, str]) -> DocumentExtraction:
    if extraction.kind != 'pdf':
        return extraction
    page_texts = dict(extraction.page_texts)
    for page_number, text in ocr_pages.items():
        clean = (text or '').strip()
        if clean:
            page_texts[int(page_number)] = clean
    joined = '\n\n'.join(
        f'[Страница {number}]\n{text}' for number, text in sorted(page_texts.items()) if text
    )
    remaining = [number for number in extraction.scanned_pages if number not in page_texts]
    return DocumentExtraction(
        text=joined,
        kind=extraction.kind,
        pages=extraction.pages,
        estimated_pages=extraction.estimated_pages,
        scanned_pages=remaining,
        page_texts=page_texts,
    )


def _split_blocks(text: str) -> list[str]:
    text = (text or '').strip()
    if not text:
        return []
    blocks: list[str] = []
    current_page = ''
    for raw in re.split(r'\n{2,}', text):
        block = raw.strip()
        if not block:
            continue
        marker = PAGE_RE.match(block)
        if marker and marker.group(0).strip() == block:
            current_page = marker.group(0).strip()
            continue
        if block.startswith('[Страница '):
            match = PAGE_RE.match(block.split('\n', 1)[0])
            if match:
                current_page = block.split('\n', 1)[0].strip()
        if current_page and not block.startswith('[Страница '):
            block = current_page + '\n' + block
        blocks.append(block)
    return blocks


def _score_block(block: str, index: int, total: int) -> float:
    low = block.lower().replace('ё', 'е')
    score = 0.0
    for term, weight in IMPORTANT_TERMS.items():
        count = low.count(term.replace('ё', 'е'))
        if count:
            score += min(count, 4) * weight
    score += min(len(DATE_RE.findall(block)), 4) * 4
    score += min(len(MONEY_RE.findall(block)), 4) * 5
    score += min(len(PERCENT_RE.findall(block)), 3) * 3
    first_line = block.splitlines()[0].strip() if block.splitlines() else ''
    if HEADING_RE.match(first_line):
        score += 3
    if index < 3:
        score += 5 - index
    if total - index <= 2:
        score += 3
    return score


def build_digest(text: str, *, fast_path_chars: int = 30_000, max_chars: int = 28_000) -> DocumentDigest:
    source = (text or '').strip()
    if len(source) <= max(1_000, int(fast_path_chars)):
        return DocumentDigest(source, len(source), 1 if source else 0, False)

    blocks = _split_blocks(source)
    if not blocks:
        return DocumentDigest(source[:max_chars], len(source), 1, True)

    total = len(blocks)
    ranked = sorted(
        ((_score_block(block, i, total), i, block) for i, block in enumerate(blocks)),
        key=lambda item: (-item[0], item[1]),
    )

    must_indexes = set(range(min(2, total)))
    must_indexes.update(range(max(0, total - 2), total))
    chosen: dict[int, str] = {i: blocks[i] for i in must_indexes}
    used = sum(len(value) + 2 for value in chosen.values())
    budget = max(4_000, int(max_chars))

    for _score, index, block in ranked:
        if index in chosen:
            continue
        cost = len(block) + 2
        if used + cost > budget:
            continue
        chosen[index] = block
        used += cost
        if used >= budget * 0.95:
            break

    ordered = [chosen[index] for index in sorted(chosen)]
    digest = '\n\n'.join(ordered)
    if len(digest) > budget:
        digest = digest[:budget].rstrip()
    return DocumentDigest(digest, len(source), len(ordered), True)


async def analyze_document_once(
    ai,
    text: str,
    kind: str,
    *,
    model: str,
    timeout: float,
    max_tokens: int,
):
    return await asyncio.wait_for(
        ai.analyze_text(text, kind, model=model, max_tokens=max_tokens),
        timeout=max(5.0, float(timeout)),
    )
