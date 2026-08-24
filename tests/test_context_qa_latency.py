from app.bot.clarify_context import _is_specific_fact_question


def test_server_penalty_question_uses_fast_fact_path():
    assert _is_specific_fact_question(
        'Какой штраф за просрочку поставки серверов и какой крайний срок поставки'
    )


def test_other_control_questions_use_fast_fact_path():
    assert _is_specific_fact_question('Что будет, если поздно оплатить лицензию на дизайн-программу?')
    assert _is_specific_fact_question('Когда арендодатель может расторгнуть договор склада и за сколько вернут депозит?')
    assert _is_specific_fact_question('Когда должен выйти мобильный релиз и что делать при критической ошибке после запуска?')


def test_broad_analysis_is_not_forced_into_fast_fact_path():
    assert not _is_specific_fact_question('Проанализируй все риски договора подробно')
