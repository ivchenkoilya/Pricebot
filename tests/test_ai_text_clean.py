from app.ai.provider import _analysis_from_raw
from app.ai.text_clean import clean_display_text


def test_clean_display_text_removes_visible_markdown_artifacts():
    raw = """## 1) Ключевые отличия

**Материал A**
- Это **страница прогноза погоды**.

---

## 2) Деньги / цены
**В материале это не указано.**
"""
    cleaned = clean_display_text(raw)
    assert '##' not in cleaned
    assert '**' not in cleaned
    assert '---' not in cleaned
    assert '1) Ключевые отличия' in cleaned
    assert 'Материал A' in cleaned
    assert 'страница прогноза погоды' in cleaned


def test_clean_display_text_keeps_lists_and_links_readable():
    raw = '* пункт один\n* пункт два\n[Источник](https://example.com)'
    cleaned = clean_display_text(raw)
    assert cleaned.startswith('• пункт один\n• пункт два')
    assert 'Источник — https://example.com' in cleaned


def test_structured_analysis_fields_are_cleaned_too():
    raw = '{"title":"**Заголовок**","summary":"## Суть\\n**Важно**","key_points":["**Факт**"],"tasks":[],"dates":[],"amounts":[],"warnings":[]}'
    result = _analysis_from_raw(raw)
    assert result.title == 'Заголовок'
    assert result.summary == 'Суть\nВажно'
    assert result.key_points == ['Факт']
