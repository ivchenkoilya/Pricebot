from __future__ import annotations

import re


def estimate_tokens(text: str) -> int:
    # Provider-agnostic conservative estimate; real usage is saved when the
    # gateway returns it.
    return max(1, len(text or '') // 3)


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
            chunks.append(part)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def retrieve_chunks(chunks: list[str], query: str, limit: int = 5) -> list[str]:
    words = {w for w in re.findall(r'[\w-]{3,}', (query or '').lower())}
    scored: list[tuple[int, int, str]] = []
    for index, chunk in enumerate(chunks):
        lowered = chunk.lower()
        score = sum(lowered.count(word) for word in words)
        scored.append((score, -index, chunk))
    scored.sort(reverse=True)
    selected = [chunk for score, _, chunk in scored[:limit] if score > 0]
    return selected or chunks[: min(limit, len(chunks))]
