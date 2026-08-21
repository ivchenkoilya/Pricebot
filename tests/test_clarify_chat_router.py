from app.bot.clarify_chat import _looks_like_general_question


def test_explicit_general_howto_ignores_recent_material():
    assert _looks_like_general_question('Как приготовить рис?', True) is True
    assert _looks_like_general_question('Что такое нейросеть?', True) is True


def test_ambiguous_followup_stays_with_recent_material():
    assert _looks_like_general_question('Когда оплатить?', True) is False
    assert _looks_like_general_question('А какой срок?', True) is False


def test_short_question_without_material_becomes_normal_chat():
    assert _looks_like_general_question('Почему небо синее?', False) is True
    assert _looks_like_general_question('Где находится Прага?', False) is True
