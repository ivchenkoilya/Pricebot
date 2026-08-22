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
    'он ', 'она ', 'они ', 'там ', 'тут ', 'здесь ', 'предыдущ', 'последн',
    'второй', 'вторая', 'втором', 'эта фраз', 'этот пункт', 'это сообщение',
    'на фото', 'на фотке', 'на фотографии', 'на картинке', 'на изображении', 'на скрине', 'на скриншоте',
    'в фото', 'в документе', 'в файле', 'в сообщении', 'в голосовом', 'в тексте',
)

# These are independent questions even when a recent material exists. This list
# prevents Clarify from answering «в материале это не указано» to ordinary chat
# such as «как приготовить рис?» or «что такое VPN?».
STANDALONE_HOWTO_PREFIXES = (
    'как сделать ', 'как создать ', 'как настроить ', 'как подключить ', 'как установить ',
    'как написать ', 'как разработать ', 'как собрать ', 'как запустить ', 'как купить ', 'как найти ',
    'как приготовить ', 'как заменить ', 'как починить ', 'как научиться ', 'как начать ', 'как выбрать ',
    'что такое ', 'кто такой ', 'кто такая ', 'расскажи про ', 'расскажи о ', 'посоветуй ', 'порекомендуй ',
    'в чем разница между ', 'в чём разница между ', 'объясни что такое ',
)

# Intent words such as «штраф», «рублей», «срок» and «риск» can also simply be
# facts inside a brand-new pasted message. We only treat them as a command about
# the previous material when the user actually phrases a request/question.
ACTION_PREFIXES = (
    'найди ', 'покажи ', 'выдели ', 'перечисли ', 'скажи ', 'проверь ', 'проанализируй ',
    'объясни ', 'сделай ', 'сократи ', 'ответь ', 'подготовь ', 'укажи ', 'посчитай ',
)
ACTION_SINGLE_PHRASES = {
    'риски', 'риск', 'штрафы', 'штраф', 'деньги', 'суммы', 'сумма', 'цена', 'стоимость', 'оплата',
    'сроки', 'срок', 'даты', 'дата', 'задачи', 'задача', 'действия', 'что делать', 'кратко', 'короче',
}

INTERROGATIVE_WORDS = re.compile(
    r'\b(кто|что|где|когда|сколько|какой|какая|какие|какого|какую|каком|каких|'
    r'почему|зачем|как|куда|откуда|чем|чей|чья|чьи)\b',
    flags=re.IGNORECASE,
)

GREETING_PHRASES = {
    'привет', 'приветик', 'здравствуй', 'здравствуйте', 'хай', 'hello', 'hey',
    'доброе утро', 'добрый день', 'добрый вечер', 'ку', 'салют',
}
ABOUT_PHRASES = {
    'кто ты', 'ты кто', 'расскажи о себе', 'что ты такое', 'что за бот',
    'зачем ты нужен', 'что такое clarify', 'кто такой clarify',
}
CAPABILITY_PHRASES = {
    'что ты умеешь', 'что умеешь', 'возможности', 'функции', 'чем можешь помочь',
    'что можешь', 'что можешь делать', 'как ты можешь помочь', 'команды', 'список команд',
    'покажи команды', 'твои возможности',
}
HELP_PHRASES = {'помощь', 'помоги разобраться', 'как пользоваться', 'как тобой пользоваться'}
EXAMPLE_PHRASES = {'примеры', 'покажи примеры', 'примеры запросов', 'что тебе написать'}
GENERAL_CHAT_PHRASES = {
    'как дела', 'как ты', 'что нового', 'спасибо', 'спс', 'благодарю', 'понял', 'понятно',
}


def _normalized_phrase(text: str) -> str:
    value = re.sub(r'\s+', ' ', (text or '').strip().lower())
    return value.strip(' .,!?:;—-()[]{}«»\"\'')


def _has_context_reference(low: str) -> bool:
    padded = f' {low} '
    return any(ref in padded for ref in CONTEXT_REFERENCES)


def _looks_like_explicit_request(value: str, low: str, phrase: str) -> bool:
    if phrase in ACTION_SINGLE_PHRASES:
        return True
    if low.startswith(QUESTION_STARTS) or low.startswith(ACTION_PREFIXES):
        return True
    # A question mark counts only for reasonably short chat questions. Long
    # pasted materials often contain quoted questions and must stay new input.
    return len(value) <= 260 and '?' in value


def looks_like_followup(text: str) -> bool:
    """Detect short requests that clearly refer to an earlier material."""
    value = re.sub(r'\s+', ' ', (text or '').strip())
    low = value.lower()
    if not value or len(value) > 240:
        return False
    if _has_context_reference(low):
        return True
    if low.startswith('а ') and (INTERROGATIVE_WORDS.search(low) or '?' in value):
        return True
    if low.startswith(('сделай короче', 'ещё короче', 'еще короче', 'объясни второй', 'а дальше')):
        return True
    return any(
        marker in low
        for marker in ('где это написано', 'что значит эта фраза', 'что имеется в виду', 'что от меня хотят')
    )


def _looks_like_context_question(value: str, low: str, has_recent_material: bool) -> bool:
    if not has_recent_material:
        return False

    has_reference = _has_context_reference(low)

    if low.startswith(STANDALONE_HOWTO_PREFIXES) and not has_reference:
        return False

    if '?' in value or low.startswith(QUESTION_STARTS):
        return True

    if len(value) <= 220 and INTERROGATIVE_WORDS.search(low) and has_reference:
        return True

    return False


def classify_text_intent(text: str, has_recent_material: bool = False) -> IntentDecision:
    """Cheap local router for UI chat, follow-ups and new material."""
    value = re.sub(r'\s+', ' ', (text or '').strip())
    low = value.lower()
    phrase = _normalized_phrase(value)

    if phrase in GREETING_PHRASES:
        return IntentDecision('greeting')
    if phrase in ABOUT_PHRASES:
        return IntentDecision('about')
    if phrase in CAPABILITY_PHRASES:
        return IntentDecision('capabilities')
    if phrase in HELP_PHRASES:
        return IntentDecision('help')
    if phrase in EXAMPLE_PHRASES:
        return IntentDecision('examples')
    if phrase in GENERAL_CHAT_PHRASES:
        return IntentDecision('general_chat')

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

    # A substantial declarative paste is a new material even if it mentions
    # money, deadlines, risks or penalties that also exist in an older item.
    # This is the common Telegram flow: paste/send material first, ask about it
    # in the next message.
    explicit_request = _looks_like_explicit_request(value, low, phrase)
    if len(value) > 260 and not explicit_request:
        return IntentDecision('new_material')

    if explicit_request and any(x in low for x in ('что от меня хотят', 'что мне нужно сделать', 'что я должен сделать', 'что нужно от меня')):
        return IntentDecision(
            'wants',
            'Скажи, что конкретно требуется от пользователя: действия, сроки, кому ответить и что подтвердить. Не выдумывай.',
            'требуется нужно сделать обязанность срок ответ подтвердить',
            has_recent_material,
        )

    if explicit_request and any(x in low for x in ('риск', 'опасн', 'штраф', 'невыгод', 'подводн')):
        return IntentDecision(
            'risks',
            'Найди риски, штрафы, ограничения, спорные и потенциально невыгодные условия. Укажи только то, что есть в материале.',
            value + ' риски штраф ответственность ограничение',
            has_recent_material,
            True,
        )

    if explicit_request and any(x in low for x in ('сумм', 'цен', 'стоим', 'оплат', 'деньг', 'руб', '₽', 'доллар', 'евро')):
        return IntentDecision(
            'money',
            'Ответь по деньгам: суммы, цена, порядок и срок оплаты, штрафы или комиссии — только по материалу.',
            value + ' сумма цена стоимость оплата платеж',
            has_recent_material,
        )

    if explicit_request and any(x in low for x in ('срок', 'дата', 'когда', 'дедлайн', 'до какого', 'крайний')):
        return IntentDecision(
            'dates',
            'Ответь по срокам и датам. Если есть несколько сроков, перечисли их с пояснением.',
            value + ' срок дата дедлайн период',
            has_recent_material,
        )

    if explicit_request and any(x in low for x in ('задач', 'что делать', 'действи')):
        return IntentDecision(
            'tasks',
            'Перечисли конкретные задачи и следующие действия. Если их нет — так и скажи.',
            value + ' задача действие сделать',
            has_recent_material,
        )

    if low in {'короче', 'ещё короче', 'еще короче', 'кратко'} or low.startswith(('сделай короче', 'сократи это')):
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
