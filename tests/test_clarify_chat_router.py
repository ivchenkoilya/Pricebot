from app.ai.intent import classify_text_intent
from app.bot.clarify_chat import _looks_like_general_question


def test_explicit_general_howto_ignores_recent_material():
    assert _looks_like_general_question('Как приготовить рис?', True) is True
    assert _looks_like_general_question('Что такое нейросеть?', True) is True
    assert classify_text_intent('Как приготовить рис?', True).uses_recent_material is False
    assert classify_text_intent('Что такое VPN?', True).uses_recent_material is False


def test_ambiguous_followup_stays_with_recent_material():
    assert _looks_like_general_question('Когда оплатить?', True) is False
    assert _looks_like_general_question('А какой срок?', True) is False
    assert classify_text_intent('Когда оплатить?', True).uses_recent_material is True
    assert classify_text_intent('А какой срок?', True).uses_recent_material is True


def test_short_question_without_material_becomes_normal_chat():
    assert _looks_like_general_question('Почему небо синее?', False) is True
    assert _looks_like_general_question('Где находится Прага?', False) is True


def test_new_declarative_text_does_not_attach_to_old_material():
    text = (
        'В понедельник утром Илье позвонил поставщик и сообщил, что заказ на 120 000 рублей '
        'задерживается примерно на три дня. Товар нужен до пятницы, потому что в субботу начинается '
        'монтаж оборудования у клиента. Если поставка не приедет вовремя, компания может потерять '
        'заказ и заплатить штраф 15 000 рублей. Илье нужно сегодня до 18:00 связаться с поставщиком, '
        'уточнить точную дату доставки и параллельно найти запасного поставщика на случай новой задержки.'
    )
    decision = classify_text_intent(text, True)
    assert decision.name == 'new_material'
    assert decision.uses_recent_material is False


def test_short_fact_with_money_or_penalty_is_also_new_material():
    decision = classify_text_intent('Заказ задержан. Штраф 15 000 рублей, оплатить до пятницы.', True)
    assert decision.name == 'new_material'
    assert decision.uses_recent_material is False


def test_explicit_risk_question_still_uses_recent_material():
    decision = classify_text_intent('Какие здесь риски и штрафы?', True)
    assert decision.name == 'risks'
    assert decision.uses_recent_material is True
