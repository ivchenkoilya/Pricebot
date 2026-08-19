from dataclasses import dataclass
from datetime import datetime, timedelta

from app.ai.conversation import (
    contextual_decision,
    extract_urls,
    select_context_materials,
    text_without_urls,
)
from app.ai.schemas import AnalysisResult


@dataclass
class MaterialStub:
    title: str
    summary: str
    extracted_text: str
    created_at: datetime
    type: str = 'text'


def test_url_extraction_cleans_telegram_punctuation():
    text = 'Посмотри https://example.com/item/42?x=1, и скажи главное.'
    assert extract_urls(text) == ['https://example.com/item/42?x=1']
    assert text_without_urls(text) == 'Посмотри и скажи главное.'


def test_contextual_decision_keeps_natural_followup():
    decision = contextual_decision('а оплатить когда?', True)
    assert decision is not None
    assert decision.uses_recent_material is True
    assert decision.name in {'money', 'dates', 'question'}


def test_contextual_decision_does_not_hijack_new_howto():
    assert contextual_decision('как сделать сайт для магазина', True) is None


def test_second_material_reference_uses_previous_item():
    now = datetime.utcnow()
    items = [
        MaterialStub('Новое фото', 'человек на улице', 'описание фото', now),
        MaterialStub('Договор', 'договор поставки', 'оплата 10 дней', now - timedelta(minutes=5), 'pdf'),
    ]
    selected = select_context_materials(items, 'а во втором когда оплата?', 12, now=now)
    assert len(selected) == 1
    assert selected[0].title == 'Договор'


def test_semanticish_recent_selection_can_jump_back():
    now = datetime.utcnow()
    items = [
        MaterialStub('Фото', 'пикник', 'люди и деревья', now),
        MaterialStub('Договор', 'гарантия и поставка', 'Гарантийный срок 12 месяцев', now - timedelta(minutes=5), 'pdf'),
        MaterialStub('Голосовое', 'встреча', 'созвон завтра', now - timedelta(minutes=10), 'voice'),
    ]
    selected = select_context_materials(items, 'что там было про гарантию?', 12, now=now)
    assert selected
    assert selected[0].title == 'Договор'


def test_compact_card_puts_direct_summary_first():
    result = AnalysisResult(
        title='Фото на улице',
        summary='На человеке маска лошади.',
        key_points=['Коричневая маска', 'Человек сидит'],
        tasks=[],
    )
    card = result.to_compact_telegram('📸 <b>Clarify</b>')
    assert 'На человеке маска лошади.' in card
    assert '<b>Коротко</b>' not in card
    assert card.index('На человеке маска лошади.') < card.index('Коричневая маска')
