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
    'какого ', 'какую ', 'каком ', 'каких ', 'почему ', 'зачем ', 'как ', 'куда ', 'откуда ',
    'чем ', 'чей ', 'чья ', 'чьи ', 'есть ли ', 'можно ли ', 'нужно ли ', 'должен ли ',
    'в какой ', 'в каком ', 'в каких ', 'на какой ', 'на каком ', 'на каких ',
    'у кого ', 'у чего ', 'из чего ', 'с чем ', 'с кем ', 'про что ', 'о чём ', 'о чем ',
    'что за ', 'кто там ', 'что там ',
)

CONTEXT_REFERENCES = (
    'этот ', 'эта ', 'это ', 'эти ', 'этого ', 'этой ', 'этом ', 'эту ',
    'тот ', 'та ', 'то ', 'те ', 'него ', 'неё ', 'нее ', 'нему ', 'ней ',
    'он ', 'она ', 'они ', 'там ', 'тут ', 'здесь ',
    'на фото', 'на фотке', 'на фотографии', 'на картинке', 'на изображении', 'на скрине', 'на скриншоте',
    'в фото', 'в документе', 'в файле', 'в сообщении', 'в голосовом', 'в тексте',
)

INTERROGATIVE_WORDS = re.compile(
    r'\b(кто|что|где|когда|сколько|какой|какая|какие|какого|какую|каком|каких|'
    r'почему|зачем|как|куда|откуда|чем|чей|чья|чьи)\b',
    flags=re.IGNORECASE,
)


def _looks_like_context_question(value: str, low: str, has_recent_material: bool) -> bool:
    if not has_recent_material:
        return False
    if '?' in value or low.startswith(QUESTION_STARTS):
        return True

    # Natural Telegram follow-ups often omit a question mark:
    # «В какой маске этот человек», «Цвет у него какой», «А это где снято».
    # Require both an interrogative and a reference to the previous material so a
    # completely new request like «как сделать сайт» is not hijacked by context.
    if len(value) <= 220 and INTERROGATIVE_WORDS.search(low):
        if any(ref in f' {low} ' for ref in CONTEXT_REFERENCES):
            return True

    return False


def classify_text_intent(text: str, has_recent_material: bool = False) -> IntentDecision:
    """Cheap local router. It avoids an extra LLM call for common follow-ups."""
    value = re.sub(r'\s+', ' ', (text or '').strip())
    low = value.lower()

    if low.startswith(('сравни ', 'сравнить ')):
        return IntentDecision('compare', deep=True)

    if low.startswith((
        'объясни просто',
        'объясни простыми словами',
        'простыми словами',
        'что это значит',
        'объясни по-простому',
    )):
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

    if _looks_like_context_question(value, low, has_recent_material):
        return IntentDecision('question', value, value, True)

    return IntentDecision('new_material')
