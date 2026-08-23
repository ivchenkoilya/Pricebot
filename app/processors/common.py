from __future__ import annotations

import re


# Families deliberately contain stems as well as full phrases. Retrieval is local
# and deterministic: no extra AI call is needed to understand common legal/work
# wording before selecting MaterialChunk rows.
CONCEPTS: dict[str, set[str]] = {
    'payment': {
        'оплат', 'платеж', 'платёж', 'расчет', 'расчёт', 'предоплат', 'аванс',
        'постоплат', 'окончательн оплат', 'денежн средств',
    },
    'price': {'цен', 'стоимост', 'сумм', 'руб', '₽', 'тариф', 'usd', 'eur'},
    'term': {
        'срок', 'дедлайн', 'период', 'дней', 'день', 'час', 'месяц', 'не позднее',
        'календарн', 'рабоч', 'банковск',
    },
    'penalty': {
        'штраф', 'пеня', 'пени', 'неустой', 'санкц', 'ответствен', 'просроч',
    },
    'delay': {
        'просроч', 'задерж', 'нарушен срок', 'нарушени срок', 'несоблюден срок',
    },
    'delivery': {
        'достав', 'постав', 'отгруз', 'передач', 'приемк', 'приёмк',
    },
    'warranty': {
        'гарант', 'гарантийн срок', 'сервис', 'ремонт', 'обслуживан', 'дефект', 'выезд специалист',
    },
    'termination': {
        'расторг', 'расторжен', 'прекращен договор', 'прекратить договор',
        'односторонн отказ', 'отказ от договора', 'отказаться от договора',
    },
    'refund': {
        'возврат', 'вернуть', 'возвратить', 'возмещ', 'вернул', 'аванс', 'предоплат',
    },
    'obligation': {
        'обязан', 'обязанност', 'должен', 'требуется', 'необходимо', 'сделать', 'предоставить',
    },
    'confidentiality': {'конфиденц', 'третьим лиц', 'разглаш'},
    'force_majeure': {'форс-мажор', 'непреодолим сил'},
    'dispute': {'спор', 'претензи', 'суд'},
}

# Backwards-compatible alias for modules/tests that imported SYNONYMS directly.
SYNONYMS = CONCEPTS

PAGE_MARKER_RE = re.compile(r'\[Страница\s+(\d+)\]', flags=re.IGNORECASE)
WORD_RE = re.compile(r'[\w₽-]{3,}', flags=re.UNICODE)
NUMBER_RE = re.compile(r'(?<!\w)\d+(?:[.,]\d+)?(?:\s*%|\s*(?:руб(?:\.|лей|ля)?|₽|дн(?:я|ей)?|час(?:а|ов)?|месяц(?:а|ев)?))?', re.I)


def estimate_tokens(text: str) -> int:
    return max(1, len(text or '') // 3)


def _normalize(text: str) -> str:
    value = (text or '').lower().replace('ё', 'е')
    value = re.sub(r'\s+', ' ', value)
    return value.strip()


def _page_prefix(text: str, start: int, part: str) -> str:
    """Carry the active page marker into a chunk cut mid-page."""
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


def _query_words(query: str) -> set[str]:
    return {word.replace('ё', 'е') for word in WORD_RE.findall(_normalize(query))}


def _query_concepts(query: str) -> set[str]:
    low = _normalize(query)
    words = _query_words(query)
    matched: set[str] = set()
    for concept, variants in CONCEPTS.items():
        if any(_normalize(variant) in low for variant in variants):
            matched.add(concept)
            continue
        # A stem like "расторг" should match "расторгнуть" in the query.
        if any(any(_normalize(variant) in word for word in words) for variant in variants if ' ' not in variant):
            matched.add(concept)
    return matched


def _query_numbers(query: str) -> set[str]:
    values: set[str] = set()
    for match in NUMBER_RE.findall(_normalize(query)):
        compact = re.sub(r'\s+', ' ', match).strip()
        if compact:
            values.add(compact)
            # The bare number is also useful when the unit wording differs.
            bare = re.match(r'\d+(?:[.,]\d+)?', compact)
            if bare:
                values.add(bare.group(0))
    return values


def score_chunk(chunk: str, query: str) -> float:
    """Return deterministic relevance score for one chunk.

    Multi-concept matches are intentionally super-linear: a clause containing
    termination + violations + refund should beat a generic chunk that merely
    repeats the word "срок" many times.
    """
    low = _normalize(chunk)
    query_low = _normalize(query)
    words = _query_words(query)
    concepts = _query_concepts(query)
    numbers = _query_numbers(query)

    score = 0.0
    if query_low and len(query_low) > 6 and query_low in low:
        score += 35.0

    matched_words = 0
    for word in words:
        if word in low:
            matched_words += 1
            count = low.count(word)
            score += min(count, 4) * (2.5 if len(word) >= 6 else 1.5)
    if matched_words >= 2:
        score += matched_words * matched_words * 1.8

    matched_concepts = 0
    for concept in concepts:
        variants = CONCEPTS[concept]
        hits = sum(1 for variant in variants if _normalize(variant) in low)
        if hits:
            matched_concepts += 1
            score += 9.0 + min(hits, 4) * 2.5
    if matched_concepts >= 2:
        score += matched_concepts * matched_concepts * 8.0

    for number in numbers:
        if number in low:
            score += 18.0

    head = low[:600]
    score += sum(2.0 for word in words if word in head)
    score += sum(4.0 for concept in concepts if any(_normalize(v) in head for v in CONCEPTS[concept]))
    return score


def retrieve_chunks(chunks: list[str], query: str, limit: int = 5) -> list[str]:
    """Local retrieval with concept, multi-term and numeric scoring.

    Only the strongest hits receive neighbouring context. This prevents generic
    neighbour chunks from displacing a distant but exact clause in long files.
    """
    if not chunks:
        return []
    limit = max(1, int(limit))
    scored = [(score_chunk(chunk, query), index) for index, chunk in enumerate(chunks)]
    scored.sort(key=lambda item: (-item[0], item[1]))
    positive = [(score, index) for score, index in scored if score > 0]
    if not positive:
        return chunks[: min(limit, len(chunks))]

    # First reserve most slots for independent high-confidence hits.
    primary_limit = min(len(positive), max(1, limit - 1))
    primary = [index for _score, index in positive[:primary_limit]]
    selected: list[int] = list(primary)

    # Add at most one neighbour for context after preserving exact distant hits.
    if len(selected) < limit and primary:
        top = primary[0]
        for candidate in (top - 1, top + 1):
            if 0 <= candidate < len(chunks) and candidate not in selected:
                selected.append(candidate)
                break

    if len(selected) < limit:
        for _score, index in positive[primary_limit:]:
            if index not in selected:
                selected.append(index)
            if len(selected) >= limit:
                break

    selected = sorted(selected[:limit])
    return [chunks[index] for index in selected]
