from __future__ import annotations

import re
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.webapp.auth import TelegramWebAppUser, runtime_context, telegram_webapp_user


router = APIRouter(prefix='/api', tags=['clarify-memory'])


class MemoryAskBody(BaseModel):
    question: str = Field(min_length=1, max_length=3000)


STOP_WORDS = {
    'как', 'что', 'где', 'когда', 'кто', 'мой', 'моя', 'мои', 'мое', 'моё', 'про', 'это', 'этот',
    'эта', 'эти', 'там', 'было', 'была', 'были', 'есть', 'для', 'или', 'мне', 'меня', 'тебе', 'свои',
    'всё', 'все', 'уже', 'ещё', 'еще', 'из', 'на', 'по', 'при', 'от', 'до', 'со', 'за', 'под',
}
WORD_RE = re.compile(r'[\wёЁ-]{3,}', re.UNICODE)


def _tg_namespace(tg: TelegramWebAppUser):
    return SimpleNamespace(id=tg.id, username=tg.username, first_name=tg.first_name or 'User')


def _terms(question: str) -> set[str]:
    return {word.lower() for word in WORD_RE.findall(question) if word.lower() not in STOP_WORDS}


def _relevance(item, terms: set[str]) -> float:
    if not terms:
        return 0.0
    title = (item.title or '').lower()
    summary = (item.summary or '').lower()
    text = (item.extracted_text or '').lower()
    score = 0.0
    for term in terms:
        if term in title:
            score += 7.0
        if term in summary:
            score += 4.0
        count = text.count(term)
        if count:
            score += min(count, 4) * 1.5
    phrase = ' '.join(sorted(terms))
    if len(phrase) > 8 and phrase in f'{title} {summary} {text}':
        score += 8.0
    return score


@router.post('/memory/ask')
async def memory_ask(
    body: MemoryAskBody,
    request: Request,
    tg: TelegramWebAppUser = Depends(telegram_webapp_user),
):
    ctx = runtime_context(request)
    user = await ctx.users.upsert(_tg_namespace(tg))
    if not await ctx.usage.allowed(user):
        raise HTTPException(429, 'Дневной лимит AI закончился')

    items = await ctx.materials.latest(user.id, 50)
    if not items:
        raise HTTPException(400, 'Материалов пока нет. Добавь первый материал.')

    terms = _terms(body.question)
    ranked = sorted(((_relevance(item, terms), item) for item in items), key=lambda pair: pair[0], reverse=True)
    selected = [item for score, item in ranked if score > 0][:6]

    # Natural questions can have little lexical overlap. A small recent fallback
    # is better than flooding the answer with every unrelated saved material.
    if not selected:
        selected = items[:3]

    parts: list[str] = []
    sources: list[dict] = []
    for index, item in enumerate(selected, 1):
        context = await ctx.materials.context(user.id, item.id, body.question, limit=3)
        if not context:
            continue
        parts.append(f'[Источник {index}: {item.title}]\n{context}')
        sources.append({'id': item.id, 'title': item.title, 'type': item.type})

    if not parts:
        raise HTTPException(400, 'Не нашёл подходящей информации в сохранённых материалах')

    prompt = (
        'Ответь на вопрос пользователя только по выбранным релевантным материалам. '
        'Сначала дай прямой ответ. Затем добавь короткие пункты только если они полезны. '
        'Не используй материал только потому, что он есть в контексте: если он не относится к вопросу, игнорируй его. '
        'Если данных недостаточно — прямо скажи это. Не выдумывай факты.'
        f'\n\nВопрос: {body.question}'
    )
    answer, usage = await ctx.ai.ask(prompt, '\n\n'.join(parts)[:48_000], model=ctx.settings.smart)
    await ctx.usage.record(user.id, ctx.settings.smart, 'webapp_memory_ask', usage)
    await ctx.metrics.inc('material_question', user.id)
    return {'answer': answer, 'sources': sources[:6]}
