from __future__ import annotations

import asyncio
from types import SimpleNamespace

import fitz
import pytest
from docx import Document

from app.ai.schemas import AnalysisResult
from app.config.settings import Settings
from app.processors.document_pipeline import (
    analyze_document_once,
    build_digest,
    estimate_pages,
    extract_for_analysis,
)
from app.processors.documents import DocumentTooLarge
from app.services.document_analysis import analyze_and_store_document


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


class _FakeMaterials:
    def __init__(self):
        self.calls = []

    async def create(self, user_id, type_, title, text, summary='', *args, **kwargs):
        self.calls.append({'user_id': user_id, 'type': type_, 'title': title, 'text': text, 'summary': summary})
        return SimpleNamespace(id=1, type=type_, title=title, extracted_text=text, summary=summary)


class _FakeUsage:
    def __init__(self):
        self.rows = []

    async def record(self, *args):
        self.rows.append(args)


@pytest.mark.asyncio
async def test_large_text_document_service_uses_one_ai_call_and_stores_full_source(tmp_path):
    source = ('Обычный раздел договора. ' * 2200) + '\n\nШтраф за просрочку 10%. Срок оплаты 15.09.2026.'
    path = tmp_path / 'large.txt'
    path.write_text(source, encoding='utf-8')

    class FakeAI:
        def __init__(self):
            self.calls = 0
            self.last_text = ''

        async def analyze_text(self, text, kind, *, model, max_tokens):
            self.calls += 1
            self.last_text = text
            return AnalysisResult(title='Договор', summary='Краткий итог'), {'input': 100, 'output': 20}, model

    settings = Settings(
        bot_token='test',
        openai_model='fast-model',
        document_fast_path_chars=5000,
        document_digest_max_chars=8000,
        document_ai_timeout=1,
        max_material_chars=200_000,
    )
    ai = FakeAI()
    materials = _FakeMaterials()
    ctx = SimpleNamespace(
        settings=settings,
        ai=ai,
        materials=materials,
        usage=_FakeUsage(),
        doc_sem=asyncio.Semaphore(1),
        ai_sem=asyncio.Semaphore(1),
    )
    user = SimpleNamespace(id=1, telegram_id=123, is_pro=False, pro_until=None, notification_settings='{}')

    item = await analyze_and_store_document(ctx, user, str(path), '.txt', 'large.txt')

    assert ai.calls == 1
    assert len(ai.last_text) <= 8000
    assert materials.calls[0]['text'] == source
    assert item.summary == 'Краткий итог'


@pytest.mark.asyncio
async def test_ai_failure_after_extract_still_saves_document(tmp_path):
    source = 'Важный текст договора и срок 15.09.2026.'
    path = tmp_path / 'contract.txt'
    path.write_text(source, encoding='utf-8')

    class FailingAI:
        async def analyze_text(self, text, kind, *, model, max_tokens):
            raise RuntimeError('provider unavailable')

    settings = Settings(bot_token='test', openai_model='fast-model', document_ai_timeout=1)
    materials = _FakeMaterials()
    ctx = SimpleNamespace(
        settings=settings,
        ai=FailingAI(),
        materials=materials,
        usage=_FakeUsage(),
        doc_sem=asyncio.Semaphore(1),
        ai_sem=asyncio.Semaphore(1),
    )
    user = SimpleNamespace(id=1, telegram_id=123, is_pro=False, pro_until=None, notification_settings='{}')

    item = await analyze_and_store_document(ctx, user, str(path), '.txt', 'contract.txt')

    assert materials.calls[0]['text'] == source
    assert 'прочитан и сохранён' in item.summary
