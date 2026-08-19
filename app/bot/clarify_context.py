from __future__ import annotations

import base64
import io
import uuid

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import Message

from app.ai.context import is_visual_followup, select_recent_image
from app.ai.conversation import contextual_decision, extract_urls, select_context_materials
from app.bot.razberi_helpers import ensure_quota, esc, get_user


def _image_mime(data: bytes) -> str:
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    return 'image/jpeg'


def build_context_router(ctx) -> Router:
    router = Router(name='clarify-context')
    settings = ctx.settings

    @router.message(F.text)
    async def visual_followup(message: Message):
        text = (message.text or '').strip()
        if not is_visual_followup(text):
            raise SkipHandler

        user = await get_user(ctx, message.from_user)
        items = await ctx.materials.latest(user.id, 8)
        material = select_recent_image(items, text, settings.recent_material_hours)
        if material is None or not material.telegram_file_id:
            raise SkipHandler

        if not await ensure_quota(ctx, message, user):
            return

        progress = await message.answer('🔎 <b>Clarify рассматривает исходное фото…</b>')
        request_id = uuid.uuid4().hex
        try:
            buffer = io.BytesIO()
            await ctx.bot.download(material.telegram_file_id, destination=buffer)
            image_bytes = buffer.getvalue()
            if not image_bytes:
                raise RuntimeError('Telegram returned an empty image')

            instruction = (
                'Ответь именно на вопрос пользователя по этому изображению: '
                f'«{text}». Внимательно рассмотри нужную визуальную деталь. '
                'Сначала дай прямой ответ в 1–2 предложениях. Затем, только если полезно, добавь короткое пояснение. '
                'Не выдумывай то, чего не видно. Если деталь невозможно уверенно определить, прямо скажи об этом. '
                'Не пытайся устанавливать личность реального человека; можно описывать только видимые признаки.'
            )
            async with ctx.ai_sem:
                answer, usage = await ctx.ai.vision(
                    base64.b64encode(image_bytes).decode(),
                    _image_mime(image_bytes),
                    instruction,
                )
            await ctx.usage.record(user.id, settings.vision, 'image_followup', usage)
            await ctx.metrics.inc('image_followups', user.id)
            await progress.edit_text('🖼 <b>Clarify</b>\n\n' + esc(answer))
        except Exception as exc:
            await ctx.errors.record(request_id, message.from_user.id, 'image_followup', exc)
            try:
                await progress.delete()
            except Exception:
                pass
            # The next contextual handler can still answer from the stored image
            # description when Telegram re-download or vision is unavailable.
            raise SkipHandler

    @router.message(F.text)
    async def conversation_followup(message: Message):
        text = (message.text or '').strip()
        if not text or extract_urls(text):
            raise SkipHandler

        user = await get_user(ctx, message.from_user)
        items = await ctx.materials.latest(user.id, 10)
        if not items:
            raise SkipHandler

        decision = contextual_decision(text, True)
        if decision is None:
            raise SkipHandler

        selected = select_context_materials(
            items,
            decision.query or text,
            settings.recent_material_hours,
            limit=3,
        )
        if not selected:
            raise SkipHandler
        if not await ensure_quota(ctx, message, user):
            return

        progress = await message.answer('🧠 <b>Clarify держит контекст…</b>')
        request_id = uuid.uuid4().hex
        try:
            contexts: list[str] = []
            for index, material in enumerate(selected, 1):
                material_context = await ctx.materials.context(
                    user.id,
                    material.id,
                    decision.query or text,
                    limit=max(2, settings.retrieval_chunk_limit - 1),
                )
                if not material_context:
                    continue
                contexts.append(
                    f'[Источник {index}: {material.title}; тип: {material.type}]\n{material_context}'
                )
            if not contexts:
                raise SkipHandler

            task = decision.prompt or text
            prompt = (
                f'{task}\n\n'
                'Это продолжение диалога. Разрешай слова «он», «она», «это», «там», «второй», «предыдущий» '
                'через переданные источники. Сначала дай прямой ответ. '
                'Если используешь факт из PDF и рядом есть маркер [Страница N], укажи страницу. '
                'Если использованы несколько материалов, в конце кратко назови, из какого материала взят каждый спорный факт. '
                'Если данных недостаточно, так и скажи — не додумывай.'
            )
            model = settings.smart if decision.deep or len(contexts) > 1 else settings.fast
            async with ctx.ai_sem:
                answer, usage = await ctx.ai.ask(prompt, '\n\n---\n\n'.join(contexts), model=model)
            await ctx.usage.record(user.id, model, f'conversation_{decision.name}', usage)
            await ctx.metrics.inc('context_followups', user.id)
            await progress.edit_text(esc(answer))
        except SkipHandler:
            try:
                await progress.delete()
            except Exception:
                pass
            raise
        except Exception as exc:
            await ctx.errors.record(request_id, message.from_user.id, 'conversation_followup', exc)
            try:
                await progress.delete()
            except Exception:
                pass
            raise SkipHandler

    return router
