from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(slots=True, frozen=True)
class IntentDecision:
    name: str
    prompt: str = ''
    query: str = ''
    uses_recent_material: bool = False
    deep: bool = False


QUESTION_STARTS = (
    'а ', 'что ', 'кто ', 'где ', 'когда ', 'сколько ', 'какой ', 'какая ', 'какие ',
    'почему ', 'зачем ', 'как ', 'есть ли ', 'можно ли ', 'нужно ли ', 'должен ли ',
)


def classify_text_intent(text: str, has_recent_material: bool = False) -> IntentDecision:
    """Cheap local router. It avoids an extra LLM call for common follow-ups."""
    value = re.sub(r'\s+', ' ', (text or '').strip())
    low = value.lower()

    if low.startswith(('сравни ', 'сравнить ')):
        return IntentDecision('compare', deep=True)

    if low.startswith(('объясни просто', 'простыми словами', 'что это значит', 'объясни по-простому')):
        return IntentDecision(
            'plain',
            'Объясни содержание простыми словами, без канцелярита. Сохрани факты, суммы и сроки.',
            value,
            has_recent_material,
        )

    if any(x in low for x in ('что от меня хотят', 'что мне нужно сделать', 'что я должен сделать', 'что нужно от меня')):
        return IntentDecision(
            'wants',
            'Скажи, что конкретно требуется от пользователя: действия, сроки, кому ответить и что подтвердить. Не выдумывай.',
            'требуется нужно сделать обязанность срок ответ подтвердить',
            has_recent_material,
        )

    if any(x in low for x in ('риск', 'опасн', 'штраф', 'невыгод', 'подводн')):
        return IntentDecision(
            'risks',
            'Найди риски, штрафы, ограничения, спорные и потенциально невыгодные условия. Укажи только то, что есть в материале.',
            value + ' риски штраф ответственность ограничение',
            has_recent_material,
            True,
        )

    if any(x in low for x in ('сумм', 'цен', 'стоим', 'оплат', 'деньг', 'руб', '₽', 'доллар', 'евро')):
        return IntentDecision(
            'money',
            'Ответь по деньгам: суммы, цена, порядок и срок оплаты, штрафы или комиссии — только по материалу.',
            value + ' сумма цена стоимость оплата платеж',
            has_recent_material,
        )

    if any(x in low for x in ('срок', 'дата', 'когда', 'дедлайн', 'до какого', 'крайний')):
        return IntentDecision(
            'dates',
            'Ответь по срокам и датам. Если есть несколько сроков, перечисли их с пояснением.',
            value + ' срок дата дедлайн период',
            has_recent_material,
        )

    if any(x in low for x in ('задач', 'что делать', 'действи', 'сделать')):
        return IntentDecision(
            'tasks',
            'Перечисли конкретные задачи и следующие действия. Если их нет — так и скажи.',
            value + ' задача действие сделать',
            has_recent_material,
        )

    if low in {'короче', 'ещё короче', 'кратко'} or low.startswith(('сделай короче', 'сократи это')):
        return IntentDecision(
            'shorten',
            'Сделай содержание заметно короче. Верни только самую полезную краткую версию.',
            'главное кратко ключевое',
            has_recent_material,
        )

    if any(x in low for x in ('ответь ему', 'ответь ей', 'что ответить', 'подготовь ответ')):
        return IntentDecision(
            'reply',
            'Подготовь короткий естественный ответ отправителю на основе материала. Верни только готовый ответ.',
            'сообщение просьба вопрос отправитель ответ',
            has_recent_material,
        )

    looks_like_question = (
        '?' in value
        or low.startswith(QUESTION_STARTS)
        or (len(value) <= 140 and any(x in low for x in ('там ', 'это ', 'ему ', 'ей ', 'здесь ')))
    )
    if has_recent_material and looks_like_question:
        return IntentDecision('question', value, value, True)

    return IntentDecision('new_material')
