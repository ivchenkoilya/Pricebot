from app.ai.intent import classify_text_intent
from app.processors.common import retrieve_chunks


def test_followup_intent_uses_recent_material():
    decision = classify_text_intent('а оплатить когда?', has_recent_material=True)
    assert decision.uses_recent_material is True
    assert decision.name in {'money', 'dates'}


def test_plain_language_intent():
    decision = classify_text_intent('объясни простыми словами', has_recent_material=True)
    assert decision.name == 'plain'
    assert decision.uses_recent_material is True


def test_risk_intent_uses_smart_mode():
    decision = classify_text_intent('какие тут риски и штрафы?', has_recent_material=True)
    assert decision.name == 'risks'
    assert decision.deep is True


def test_retrieval_understands_payment_synonyms():
    chunks = [
        'Общие положения договора и реквизиты сторон.',
        'Покупатель перечисляет аванс 30 процентов в течение трех рабочих дней.',
        'Гарантийный срок составляет двенадцать месяцев.',
    ]
    selected = retrieve_chunks(chunks, 'когда нужно оплатить?', limit=2)
    assert any('аванс' in item.lower() for item in selected)


def test_retrieval_understands_penalty_synonyms():
    chunks = [
        'Стоимость товара составляет 50 000 рублей.',
        'За просрочку начисляется пеня 0,1 процента за каждый день.',
        'Поставка осуществляется транспортной компанией.',
    ]
    selected = retrieve_chunks(chunks, 'есть ли штраф?', limit=2)
    assert any('пеня' in item.lower() for item in selected)
