from __future__ import annotations

import asyncio

import fitz
import pytest
from docx import Document

from app.ai.schemas import AnalysisResult
from app.processors.document_pipeline import (
    analyze_document_once,
    build_digest,
    estimate_pages,
    extract_for_analysis,
)
from app.processors.documents import DocumentTooLarge


def test_estimate_pages_is_predictable():
    assert estimate_pages('а' * 2500, 2500) == 1
    assert estimate_pages('а' * 2501, 2500) == 2
    assert estimate_pages('', 2500) == 0


def test_large_document_digest_is_bounded_and_keeps_important_terms():
    ordinary = [f'Раздел {i}\nОбычный информационный текст ' + ('описание ' * 80) for i in range(80)]
    ordinary.insert(43, 'Ответственность сторон\nШтраф за просрочку составляет 10% от суммы договора. Срок оплаты — 15.09.2026.')
    source = '\n\n'.join(ordinary)

    digest = build_digest(source, fast_path_chars=5000, max_chars=9000)

    assert digest.used_digest is True
    assert len(digest.text) <= 9000
    assert 'Штраф за просрочку' in digest.text
    assert '15.09.2026' in digest.text
    assert digest.selected_blocks < len(ordinary)


@pytest.mark.asyncio
async def test_initial_document_analysis_uses_exactly_one_ai_call():
    class FakeAI:
        def __init__(self):
            self.calls = 0

        async def analyze_text(self, text, kind, *, model, max_tokens):
            self.calls += 1
            return AnalysisResult(summary='Готово'), {'input': 10, 'output': 2}, model

    ai = FakeAI()
    result, usage, model = await analyze_document_once(
        ai,
        'Короткий документ',
        'docx-документ',
        model='fast-model',
        timeout=1,
        max_tokens=300,
    )

    assert ai.calls == 1
    assert result.summary == 'Готово'
    assert usage['input'] == 10
    assert model == 'fast-model'


@pytest.mark.asyncio
async def test_document_analysis_timeout_is_bounded():
    class SlowAI:
        async def analyze_text(self, text, kind, *, model, max_tokens):
            await asyncio.sleep(0.05)
            return AnalysisResult(summary='Поздно'), {}, model

    with pytest.raises(asyncio.TimeoutError):
        await analyze_document_once(
            SlowAI(),
            'Документ',
            'docx-документ',
            model='fast-model',
            timeout=0.01,
            max_tokens=100,
        )


def test_docx_gets_estimated_page_limit(tmp_path):
    path = tmp_path / 'large.docx'
    doc = Document()
    doc.add_paragraph('Очень длинный договор. ' + ('условия поставки и оплаты ' * 500))
    doc.save(path)

    with pytest.raises(DocumentTooLarge, match='примерно'):
        extract_for_analysis(
            str(path),
            '.docx',
            2,
            chars_per_page=1000,
            max_text_chars=100_000,
        )


def test_text_pdf_does_not_require_ocr(tmp_path):
    path = tmp_path / 'text.pdf'
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), 'This is a normal text PDF page with enough selectable text for Clarify analysis.')
    doc.save(path)
    doc.close()

    result = extract_for_analysis(str(path), '.pdf', 10)

    assert result.pages == 1
    assert result.scanned_pages == []
    assert 'normal text PDF' in result.text
    assert '[Страница 1]' in result.text


def test_mixed_pdf_marks_only_blank_page_for_ocr(tmp_path):
    path = tmp_path / 'mixed.pdf'
    doc = fitz.open()
    page1 = doc.new_page()
    page1.insert_text((72, 72), 'Selectable contract text on page one. Payment deadline is ten days after delivery.')
    doc.new_page()
    doc.save(path)
    doc.close()

    result = extract_for_analysis(str(path), '.pdf', 10)

    assert result.pages == 2
    assert result.scanned_pages == [2]
    assert '[Страница 1]' in result.text
