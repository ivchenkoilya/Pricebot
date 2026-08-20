from __future__ import annotations

from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.webapp.auth import TelegramWebAppUser, runtime_context, telegram_webapp_user


router = APIRouter(prefix='/api', tags=['clarify-memory'])


class MemoryAskBody(BaseModel):
    question: str = Field(min_length=1, max_length=3000)


def _tg_namespace(tg: TelegramWebAppUser):
    return SimpleNamespace(id=tg.id, username=tg.username, first_name=tg.first_name or 'User')


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

    items = await ctx.materials.latest(user.id, 20)
    if not items:
        raise HTTPException(400, 'Memory пока пустая. Добавь первый материал.')

    parts: list[str] = []
    sources: list[dict] = []
    for index, item in enumerate(items[:12], 1):
        context = await ctx.materials.context(user.id, item.id, body.question, limit=2)
        if not context:
            continue
        parts.append(f'[Источник {index}: {item.title}]\n{context}')
        sources.append({'id': item.id, 'title': item.title, 'type': item.type})

    if not parts:
        raise HTTPException(400, 'Не нашёл подходящего контекста в Memory')

    prompt = (
        'Ответь на вопрос пользователя только по его сохранённым материалам. '
        'Сначала дай прямой ответ, затем 2–6 коротких пунктов, если это полезно. '
        'Если данных недостаточно — прямо скажи это. Укажи названия использованных материалов.'
        f'\n\nВопрос: {body.question}'
    )
    answer, usage = await ctx.ai.ask(prompt, '\n\n'.join(parts)[:48_000], model=ctx.settings.smart)
    await ctx.usage.record(user.id, ctx.settings.smart, 'webapp_memory_ask', usage)
    return {'answer': answer, 'sources': sources[:8]}
