from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from app.processors.common import SYNONYMS


WORD_RE = re.compile(r'[\wёЁ₽-]{3,}', re.UNICODE)
DATE_RE = re.compile(
    r'\b(?:сегодня|завтра|послезавтра|до\s+\d{1,2}(?:[./-]\d{1,2}(?:[./-]\d{2,4})?)?|'
    r'\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)|'
    r'\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?)\b',
    re.IGNORECASE,
)
TASK_RE = re.compile(
    r'\b(?:нужно|надо|необходимо|требуется|должен|должна|должны|сделать|отправить|'
    r'ответить|оплатить|подписать|проверить|согласовать|позвонить|купить|предоставить)\b',
    re.IGNORECASE,
)
RISK_RE = re.compile(
    r'\b(?:риск|штраф|пен[ия]|неустойк\w*|просроч\w*|ответственност\w*|опасн\w*|'
    r'ограничен\w*|блокировк\w*|нарушен\w*)\b',
    re.IGNORECASE,
)

STOP_WORDS = {
    'как', 'что', 'где', 'когда', 'кто', 'какой', 'какая', 'какие', 'мой', 'моя', 'мои',
    'это', 'этот', 'эта', 'эти', 'там', 'тут', 'здесь', 'про', 'мне', 'меня', 'тебе',
    'для', 'или', 'уже', 'ещё', 'еще', 'было', 'была', 'были', 'есть', 'найди', 'покажи',
    'материал', 'материалы', 'memory', 'память', 'памяти', 'clarify',
}


@dataclass(slots=True, frozen=True)
class CopilotCommand:
    kind: str
    value: str = ''


@dataclass(slots=True)
class SearchHit:
    item: object
    score: float
    snippet: str


def _stem(term: str) -> str:
    value = term.lower().replace('ё', 'е')
    for suffix in (
        'иями', 'ями', 'ами', 'ого', 'ему', 'ому', 'ыми', 'ими', 'овать', 'ировать',
        'ение', 'ений', 'енная', 'енный', 'ую', 'юю', 'ая', 'яя', 'ое', 'ее', 'ие', 'ые',
        'ий', 'ый', 'ой', 'ам', 'ям', 'ах', 'ях', 'ом', 'ем', 'ов', 'ев', 'ы', 'и', 'а',
        'я', 'у', 'ю', 'е',
    ):
        if value.endswith(suffix) and len(value) - len(suffix) >= 5:
            return value[:-len(suffix)]
    return value


def query_terms(value: str) -> set[str]:
    words = {w.lower().replace('ё', 'е') for w in WORD_RE.findall(value or '')}
    words = {w for w in words if w not in STOP_WORDS}
    expanded = set(words)
    for root, variants in SYNONYMS.items():
        family = {root.replace('ё', 'е'), *(v.replace('ё', 'е') for v in variants)}
        if words & family:
            expanded |= family
    return expanded


def _clean_snippet(text: str, limit: int = 180) -> str:
    value = re.sub(r'\s+', ' ', text or '').strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip(' ,.;:-') + '…'


def _best_snippet(item, terms: set[str]) -> str:
    summary = str(getattr(item, 'summary', '') or '')
    text = str(getattr(item, 'extracted_text', '') or '')
    if summary:
        low = summary.lower().replace('ё', 'е')
        if not terms or any(_stem(term) in low for term in terms):
            return _clean_snippet(summary)
    if text:
        low = text.lower().replace('ё', 'е')
        positions = [low.find(_stem(term)) for term in terms if len(_stem(term)) >= 4 and low.find(_stem(term)) >= 0]
        if positions:
            start = max(0, min(positions) - 70)
            return _clean_snippet(text[start:start + 260])
        return _clean_snippet(text)
    return _clean_snippet(str(getattr(item, 'title', '') or 'Материал'))


def rank_materials(items: Iterable[object], query: str, limit: int = 8) -> list[SearchHit]:
    """Rank materials by lexical meaning, light stemming, synonyms and recency.

    This intentionally stays local and fast so global Memory search does not spend
    an AI request just to find likely source materials.
    """
    terms = query_terms(query)
    phrase = re.sub(r'\s+', ' ', (query or '').lower().replace('ё', 'е')).strip()
    hits: list[SearchHit] = []
    for index, item in enumerate(items):
        title = str(getattr(item, 'title', '') or '')
        summary = str(getattr(item, 'summary', '') or '')
        text = str(getattr(item, 'extracted_text', '') or '')[:24_000]
        title_low = title.lower().replace('ё', 'е')
        summary_low = summary.lower().replace('ё', 'е')
        text_low = text.lower().replace('ё', 'е')
        whole = f'{title_low}\n{summary_low}\n{text_low}'
        score = max(0.0, 2.0 - index * 0.025)
        if phrase and len(phrase) >= 6 and phrase in whole:
            score += 14.0
        for term in terms:
            stem = _stem(term)
            candidates = {term, stem}
            if any(candidate and candidate in title_low for candidate in candidates):
                score += 8.0
            if any(candidate and candidate in summary_low for candidate in candidates):
                score += 4.5
            occurrences = max((text_low.count(candidate) for candidate in candidates if candidate), default=0)
            score += min(occurrences, 4) * 1.5
        if terms and score <= 2.05:
            continue
        hits.append(SearchHit(item=item, score=score, snippet=_best_snippet(item, terms)))
    hits.sort(key=lambda hit: hit.score, reverse=True)
    return hits[:limit]


def detect_copilot_command(text: str) -> CopilotCommand | None:
    value = re.sub(r'\s+', ' ', (text or '').strip())
    low = value.lower().replace('ё', 'е')
    if not value:
        return None

    if any(phrase in low for phrase in (
        'что срочного', 'что мне нужно сделать', 'что нужно сделать', 'мои задачи', 'покажи задачи',
        'какие задачи', 'мои дедлайны', 'покажи дедлайны', 'что на сегодня', 'что важно сегодня',
    )):
        return CopilotCommand('inbox')

    if any(phrase in low for phrase in (
        'последние материалы', 'покажи материалы', 'мои материалы', 'что я отправлял недавно',
    )):
        return CopilotCommand('recent_materials')

    project = re.match(r'^(?:создай|создать|новый)\s+проект(?:\s+(?:с названием|под названием))?\s+(.+)$', value, re.I)
    if project:
        name = project.group(1).strip(' «»"\'.,')[:120]
        if name:
            return CopilotCommand('create_project', name)

    search = re.match(
        r'^(?:найди|найти|покажи|отыщи|вспомни)\s+(?:мне\s+)?(?:в\s+(?:memory|памяти|материалах)\s+)?(.+)$',
        value,
        re.I,
    )
    if search:
        query = search.group(1).strip(' .,:;-')
        query = re.sub(r'^(?:материал|материалы|где|то|что)\s+', '', query, flags=re.I)
        if len(query) >= 3:
            return CopilotCommand('memory_search', query)

    return None


def _sentence_with_match(text: str, pattern: re.Pattern[str]) -> str:
    value = re.sub(r'\s+', ' ', text or '').strip()
    if not value:
        return ''
    for sentence in re.split(r'(?<=[.!?])\s+', value):
        if pattern.search(sentence):
            return _clean_snippet(sentence, 190)
    return _clean_snippet(value, 190)


def build_inbox(items: Iterable[object], reminders: Iterable[object] = (), limit: int = 8) -> dict:
    signals: list[dict] = []
    task_count = 0
    deadline_count = 0
    risk_count = 0

    for item in items:
        material_id = getattr(item, 'id', None)
        title = str(getattr(item, 'title', '') or 'Материал')
        content = ' '.join([
            str(getattr(item, 'summary', '') or ''),
            str(getattr(item, 'extracted_text', '') or '')[:3500],
        ]).strip()
        if not content:
            continue
        if TASK_RE.search(content):
            task_count += 1
            signals.append({'kind': 'task', 'material_id': material_id, 'title': title, 'text': _sentence_with_match(content, TASK_RE)})
        if DATE_RE.search(content):
            deadline_count += 1
            signals.append({'kind': 'deadline', 'material_id': material_id, 'title': title, 'text': _sentence_with_match(content, DATE_RE)})
        if RISK_RE.search(content):
            risk_count += 1
            signals.append({'kind': 'risk', 'material_id': material_id, 'title': title, 'text': _sentence_with_match(content, RISK_RE)})
        if len(signals) >= limit * 3:
            break

    active_reminders = 0
    now = datetime.utcnow()
    for reminder in reminders:
        if str(getattr(reminder, 'status', '')) != 'active':
            continue
        remind_at = getattr(reminder, 'remind_at', None)
        if remind_at and remind_at < now:
            continue
        active_reminders += 1
        deadline_count += 1
        signals.insert(0, {
            'kind': 'reminder',
            'material_id': None,
            'title': 'Напоминание',
            'text': _clean_snippet(str(getattr(reminder, 'text', '') or 'Напоминание')),
            'remind_at': remind_at.isoformat() + 'Z' if remind_at else None,
        })

    # Deduplicate repeated signal text while preserving reminder/task priority.
    unique: list[dict] = []
    seen: set[tuple[str, str]] = set()
    order = {'reminder': 0, 'deadline': 1, 'task': 2, 'risk': 3}
    signals.sort(key=lambda signal: order.get(signal.get('kind', ''), 9))
    for signal in signals:
        key = (signal.get('kind', ''), signal.get('text', '').lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(signal)
        if len(unique) >= limit:
            break

    return {
        'tasks': task_count,
        'deadlines': deadline_count,
        'risks': risk_count,
        'active_reminders': active_reminders,
        'items': unique,
    }
