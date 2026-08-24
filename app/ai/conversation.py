from __future__ import annotations

import re
from datetime import datetime, timedelta

from app.ai.intent import IntentDecision, classify_text_intent
from app.utils.url import find_urls, strip_urls


WORD_RE = re.compile(r'[\w₽-]{3,}', flags=re.IGNORECASE)

REFERENCE_MARKERS = (
    'это', 'этот', 'эта', 'эти', 'там', 'тут', 'здесь', 'он', 'она', 'они',
    'него', 'неё', 'нее', 'нему', 'ней', 'по нему', 'по ней', 'в нём', 'в нем',
    'первый', 'первая', 'второй', 'вторая', 'предыдущий', 'предыдущая',
    'последний', 'последняя', 'тот', 'та', 'то', 'те', 'а теперь', 'а если',
)


def extract_urls(text: str, limit: int = 3) -> list[str]:
    return find_urls(text, limit=limit)


def text_without_urls(text: str) -> str:
    return strip_urls(text)


def contextual_decision(text: str, has_recent_material: bool) -> IntentDecision | None:
    if not has_recent_material:
        return None
    decision = classify_text_intent(text, True)
    if decision.name == 'compare':
        return None
    if decision.uses_recent_material:
        return decision
    low = ' '.join((text or '').lower().split())
    if len(low) <= 220 and any(marker in low for marker in REFERENCE_MARKERS):
        return IntentDecision('conversation', text, text, True)
    return None


def _is_recent(item, recent_hours: int, now: datetime) -> bool:
    created = getattr(item, 'created_at', None)
    return bool(created and now - created <= timedelta(hours=recent_hours))


def _terms(value: str) -> set[str]:
    stop = {
        'что', 'это', 'этот', 'эта', 'эти', 'как', 'где', 'когда', 'какой', 'какая',
        'какие', 'там', 'тут', 'здесь', 'него', 'нее', 'неё', 'ему', 'ней', 'или',
        'для', 'про', 'под', 'над', 'при', 'мне', 'моя', 'мой', 'твой', 'ещё', 'еще',
        'было', 'была', 'были', 'будет', 'есть', 'тогда', 'теперь', 'сказано',
    }
    return {term.lower() for term in WORD_RE.findall(value or '') if term.lower() not in stop}


def _stem(term: str) -> str:
    """Tiny Russian-friendly stemmer for retrieval, not linguistic analysis."""
    for suffix in (
        'иями', 'ями', 'ами', 'ого', 'ему', 'ому', 'ыми', 'ими', 'ую', 'юю',
        'ая', 'яя', 'ое', 'ее', 'ие', 'ые', 'ий', 'ый', 'ой', 'ам', 'ям', 'ах',
        'ях', 'ом', 'ем', 'ов', 'ев', 'ы', 'и', 'а', 'я', 'у', 'ю', 'е',
    ):
        if term.endswith(suffix) and len(term) - len(suffix) >= 5:
            return term[:-len(suffix)]
    return term


def select_context_materials(
    items,
    query: str,
    recent_hours: int,
    *,
    limit: int = 3,
    now: datetime | None = None,
):
    """Select a tiny conversation working set from recent materials.

    Recency is the default signal; lexical overlap lets a follow-up jump back to
    another recent file without sending the whole history to the model.
    """
    now = now or datetime.utcnow()
    recent = [item for item in items if _is_recent(item, recent_hours, now)]
    if not recent:
        return []

    low = ' '.join((query or '').lower().split())
    terms = _terms(query)

    # Natural ordinal references are resolved against recency order.
    if any(word in low for word in ('предыдущ', 'второй', 'вторая', 'втором')) and len(recent) > 1:
        return [recent[1]]
    if any(word in low for word in ('третий', 'третья', 'третьем')) and len(recent) > 2:
        return [recent[2]]

    # Explicit demonstratives mean the newest item. Weak locatives like «там»
    # only do that when the question has no meaningful topic words.
    if any(word in low for word in ('последн', 'этот', 'эта ', 'это ')):
        return [recent[0]]
    if not terms and any(word in low for word in ('там', 'тут', 'здесь')):
        return [recent[0]]

    scored: list[tuple[float, int, object]] = []
    for index, item in enumerate(recent[:10]):
        haystack = ' '.join(
            [
                str(getattr(item, 'title', '') or ''),
                str(getattr(item, 'summary', '') or ''),
                str(getattr(item, 'extracted_text', '') or '')[:3000],
            ]
        ).lower()
        overlap = 0
        for term in terms:
            stem = _stem(term)
            if term in haystack or (len(stem) >= 5 and stem in haystack):
                overlap += 1
        score = overlap * 3.0 + max(0.0, 2.0 - index * 0.25)
        scored.append((score, index, item))

    scored.sort(key=lambda row: (-row[0], row[1]))
    positive = [item for score, _, item in scored if score > 2.0][:limit]
    return positive or [recent[0]]
