from types import SimpleNamespace

from app.webapp.memory import _relevance, _terms


def material(title: str, summary: str, text: str):
    return SimpleNamespace(title=title, summary=summary, extracted_text=text)


def test_memory_prefers_relevant_material_over_recent_noise():
    terms = _terms('Как меня зовут и что было про зарплату?')
    relevant = material('Илья о зарплате', 'Планы и выплаты', 'Меня зовут Илья. Зарплата обсуждалась отдельно.')
    noise = material('YouTube видео', 'Ролик про новости', 'Полиция, школа и комментарии.')
    assert _relevance(relevant, terms) > _relevance(noise, terms)
    assert _relevance(relevant, terms) > 0


def test_memory_terms_drop_generic_stop_words():
    terms = _terms('Что там было про проект Clarify?')
    assert 'что' not in terms
    assert 'там' not in terms
    assert 'проект' in terms
    assert 'clarify' in terms
