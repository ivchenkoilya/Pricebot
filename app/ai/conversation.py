from __future__ import annotations

import re
from datetime import datetime, timedelta

from app.ai.intent import IntentDecision, classify_text_intent


URL_RE = re.compile(r'https?://[^\s<>"\']+', flags=re.IGNORECASE)
WORD_RE = re.compile(r'[\w₽-]{3,}', flags=re.IGNORECASE)

REFERENCE_MARKERS = (
    'это', 'этот', 'эта', 'эти', 'там', 'тут', 'здесь', 'он', 'она', 'они',
    'него', 'неё', 'нее', 'нему', 'ней', 'по нему', 'по ней', 'в нём', 'в нем',
    'первый', 'первая', 'второй', 'вторая', 'предыдущий', 'предыдущая',
    'последний', 'последняя', 'тот', 'та', 'то', 'те', 'а теперь', 'а если',
)


def extract_urls(text: str, limit: int = 3) -> list[str]:
    urls: list[str] = []
    for match in URL_RE.findall(text or ''):
        clean = match.rstrip('.,;:!?)]}»')
        if clean and clean not in urls:
            urls.append(clean)
        if len(urls) >= limit:
            break
    return urls


def text_without_urls(text: str) -> str:
    value = URL_RE.sub(' ', text or '')
    return re.sub(r'\s+', ' ', value).strip(' \n\t-—:')


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
    }
    return {term.lower() for term in WORD_RE.findall(value or '') if term.lower() not in stop}


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
    # Natural ordinal references are resolved against recency order.
    if any(word in low for word in ('предыдущ', 'второй', 'вторая', 'втором')) and len(recent) > 1:
        return [recent[1]]
    if any(word in low for word in ('третий', 'третья', 'третьем')) and len(recent) > 2:
        return [recent[2]]
    if any(word in low for word in ('последн', 'этот', 'эта ', 'это ', 'там', 'тут', 'здесь')):
        return [recent[0]]

    terms = _terms(query)
    scored: list[tuple[float, int, object]] = []
    for index, item in enumerate(recent[:10]):
        haystack = ' '.join(
            [
                str(getattr(item, 'title', '') or ''),
                str(getattr(item, 'summary', '') or ''),
                str(getattr(item, 'extracted_text', '') or '')[:3000],
            ]
        ).lower()
        overlap = sum(1 for term in terms if term in haystack)
        score = overlap * 3.0 + max(0.0, 2.0 - index * 0.25)
        scored.append((score, index, item))

    scored.sort(key=lambda row: (-row[0], row[1]))
    positive = [item for score, _, item in scored if score > 2.0][:limit]
    return positive or [recent[0]]
