from __future__ import annotations

import asyncio
import base64
import io
import re
import uuid

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import Message

from app.ai.context import is_visual_followup, select_recent_image
from app.ai.conversation import contextual_decision, extract_urls, select_context_materials
from app.bot.razberi_helpers import ensure_quota, esc, get_user


_SPECIFIC_QUESTION_RE = re.compile(
    r'^(?:а\s+)?(?:какой|какая|какие|какого|какую|когда|сколько|где|кто|что|'
    r'есть ли|можно ли|нужно ли|должен ли|в какой|в каком|на какой|до какого)\b',
    flags=re.IGNORECASE,
)


def _is_specific_fact_question(text: str) -> bool:
    """Detect short factual follow-ups that should use the fast exact-answer path.

    A question such as «Какой штраф ... и какой крайний срок?» used to be
    classified as broad risk analysis and sent to the smart model. That made a
    one-fact lookup unnecessarily slow and also widened the answer. Short
    interrogative questions now keep the user's wording and go to the fast model.
    """
    value = re.sub(r'\s+', ' ', (text or '').strip())
    if not value or len(value) > 320:
        return False
    return bool(_SPECIFIC_QUESTION_RE.search(value) or '?' in value)


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
        items = await ctx.conversations.recent_materials(user.id, 8)
        material = select_recent_image(items, text, settings.recent_material_hours)
        if material is None or not material.telegram_file_id:
            raise SkipHandler

        if not await ensure_quota(ctx, message, user):
            return

        progress = await message.answer('🖼 <b>Изучаю исходное изображение…</b>')
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
            ctx.conversations.remember(user.id, 'user', text)
            ctx.conversations.remember(user.id, 'assistant', answer)
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
        items = await ctx.conversations.recent_materials(user.id, 10)
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

        progress = await message.answer('🧠 <b>Уточняю по последнему материалу…</b>')
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
                try:
                    await progress.delete()
                except Exception:
                    pass
                raise SkipHandler

            specific_question = _is_specific_fact_question(text)
            # Preserve the literal question for factual lookups. Previously an
            # intent such as "risks" replaced it with a broad prompt, so
            # "Какой штраф и какой срок?" became a slow full risk analysis.
            task = text if specific_question else (decision.prompt or text)
            recent_dialogue = ctx.conversations.history_text(user.id, limit=6)
            dialogue_note = (
                '\n\nНедавний диалог (используй только для разрешения коротких ссылок и продолжения мысли):\n'
                + recent_dialogue
                if recent_dialogue else ''
            )
            prompt = (
                f'{task}\n\n'
                'Это продолжение диалога. Разрешай слова «он», «она», «это», «там», «второй», «предыдущий» '
                'через переданные источники. Сначала дай прямой ответ. '
                'Отвечай только на заданный вопрос и не перечисляй соседние условия без необходимости. '
                'Если используешь факт и рядом есть маркер [Страница N], укажи только страницу, непосредственно подтверждающую ответ. '
                'Если использованы несколько материалов, в конце кратко назови, из какого материала взят каждый спорный факт. '
                'Если данных недостаточно, так и скажи — не додумывай.'
                f'{dialogue_note}'
            )

            # A short factual follow-up must be fast. Smart is kept for genuinely
            # broad/deep requests, but every call has a hard deadline so Telegram
            # never sits on "Уточняю..." for minutes.
            model = settings.fast if specific_question else (
                settings.smart if decision.deep or len(contexts) > 1 else settings.fast
            )
            primary_timeout = 20.0 if model == settings.fast else 18.0

            try:
                async with ctx.ai_sem:
                    answer, usage = await asyncio.wait_for(
                        ctx.ai.ask(prompt, '\n\n---\n\n'.join(contexts), model=model),
                        timeout=primary_timeout,
                    )
            except asyncio.TimeoutError:
                if model == settings.fast:
                    await ctx.metrics.inc('context_followup_timeouts', user.id)
                    await progress.edit_text(
                        '⚠️ <b>Ответ занял слишком много времени</b>\n\n'
                        'Я остановил запрос, чтобы Clarify не зависал на несколько минут. Попробуй задать вопрос ещё раз.'
                    )
                    return

                # Broad smart request gets one short fast fallback, never another
                # long smart retry.
                model = settings.fast
                fallback_prompt = (
                    f'{text}\n\nОтветь только на этот вопрос по переданным фрагментам. '
                    'Коротко, точно, без общего пересказа. Укажи точную страницу факта, если она размечена.'
                )
                try:
                    async with ctx.ai_sem:
                        answer, usage = await asyncio.wait_for(
                            ctx.ai.ask(
                                fallback_prompt,
                                '\n\n---\n\n'.join(contexts),
                                model=model,
                            ),
                            timeout=10.0,
                        )
                    await ctx.metrics.inc('context_fast_fallbacks', user.id)
                except asyncio.TimeoutError:
                    await ctx.metrics.inc('context_followup_timeouts', user.id)
                    await progress.edit_text(
                        '⚠️ <b>AI отвечает дольше обычного</b>\n\n'
                        'Я остановил запрос вместо бесконечного ожидания. Попробуй ещё раз через несколько секунд.'
                    )
                    return

            await ctx.usage.record(user.id, model, f'conversation_{decision.name}', usage)
            await ctx.metrics.inc('context_followups', user.id)
            ctx.conversations.remember(user.id, 'user', text)
            ctx.conversations.remember(user.id, 'assistant', answer)
            await progress.edit_text(esc(answer))
        except SkipHandler:
            raise
        except Exception as exc:
            await ctx.errors.record(request_id, message.from_user.id, 'conversation_followup', exc)
            # Once we have positively selected recent material, do not let an AI
            # error fall through and turn the user's question into a new Material.
            try:
                await progress.edit_text(
                    '⚠️ <b>Не получилось ответить по материалу</b>\n\n'
                    'Сам материал сохранён. Попробуй повторить вопрос через несколько секунд.'
                )
            except Exception:
                pass
            return

    return router
