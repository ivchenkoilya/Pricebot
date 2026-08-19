from __future__ import annotations

import re


SYNONYMS = {
    'оплата': {'платеж', 'оплатить', 'расчет', 'расчёт', 'предоплата', 'аванс', 'постоплата'},
    'цена': {'стоимость', 'сумма', 'руб', 'рублей', '₽', 'тариф'},
    'срок': {'дата', 'дедлайн', 'период', 'дней', 'день', 'до', 'не позднее'},
    'штраф': {'пеня', 'пени', 'неустойка', 'ответственность', 'санкция'},
    'доставка': {'поставка', 'поставить', 'отгрузка', 'передача', 'приемка', 'приёмка'},
    'гарантия': {'гарантийный', 'гарантийная', 'ремонт', 'дефект'},
    'задача': {'обязан', 'обязанность', 'должен', 'требуется', 'необходимо', 'сделать'},
}

PAGE_MARKER_RE = re.compile(r'\[Страница\s+(\d+)\]', flags=re.IGNORECASE)


def estimate_tokens(text: str) -> int:
    return max(1, len(text or '') // 3)


def _page_prefix(text: str, start: int, part: str) -> str:
    """Carry the active PDF page marker into a chunk cut mid-page."""
    if start <= 0 or PAGE_MARKER_RE.match(part):
        return ''
    matches = list(PAGE_MARKER_RE.finditer(text, 0, start))
    if not matches:
        return ''
    return f'[Страница {matches[-1].group(1)}]\n'


def chunk_text(text: str, size: int = 8_000, overlap: int = 500) -> list[str]:
    text = (text or '').strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            search_from = start + size // 2
            candidates = [
                text.rfind('\n\n', search_from, end),
                text.rfind('\n', search_from, end),
                text.rfind('. ', search_from, end),
            ]
            cut = max(candidates)
            if cut > start:
                end = cut + 1
        part = text[start:end].strip()
        if part:
            prefix = _page_prefix(text, start, part)
            chunks.append(prefix + part)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _query_terms(query: str) -> set[str]:
    words = {w for w in re.findall(r'[\w₽-]{3,}', (query or '').lower())}
    expanded = set(words)
    for root, variants in SYNONYMS.items():
        family = {root, *variants}
        if words & family:
            expanded |= family
    return expanded


def retrieve_chunks(chunks: list[str], query: str, limit: int = 5) -> list[str]:
    """Lexical retrieval with domain synonyms plus neighbouring context."""
    if not chunks:
        return []
    terms = _query_terms(query)
    query_low = (query or '').lower().strip()
    scored: list[tuple[float, int]] = []
    for index, chunk in enumerate(chunks):
        lowered = chunk.lower()
        score = 0.0
        if query_low and len(query_low) > 6 and query_low in lowered:
            score += 12.0
        for term in terms:
            count = lowered.count(term)
            if count:
                score += min(count, 6) * (2.0 if len(term) >= 6 else 1.0)
        # Headings and first lines often carry section semantics.
        head = lowered[:500]
        score += sum(1.5 for term in terms if term in head)
        scored.append((score, index))

    scored.sort(key=lambda item: (-item[0], item[1]))
    positive = [index for score, index in scored if score > 0][:limit]
    if not positive:
        return chunks[: min(limit, len(chunks))]

    # Include one neighbour around top hits to preserve clauses split at chunk boundaries.
    selected_indexes: list[int] = []
    for index in positive:
        for candidate in (index, index - 1, index + 1):
            if 0 <= candidate < len(chunks) and candidate not in selected_indexes:
                selected_indexes.append(candidate)
            if len(selected_indexes) >= limit:
                break
        if len(selected_indexes) >= limit:
            break
    selected_indexes.sort()
    return [chunks[index] for index in selected_indexes]
