from __future__ import annotations

import base64
import io
import uuid

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import Message

from app.ai.context import is_visual_followup, select_recent_image
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
        items = await ctx.materials.latest(user.id, 6)
        material = select_recent_image(items, text, settings.recent_material_hours)
        if material is None or not material.telegram_file_id:
            raise SkipHandler

        if not await ensure_quota(ctx, message, user):
            return

        progress = await message.answer('🔎 <b>Clarify смотрит исходное фото ещё раз…</b>')
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
                'Отвечай коротко и конкретно. Не выдумывай то, чего не видно. '
                'Если деталь невозможно уверенно определить, прямо скажи об этом. '
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
            await progress.edit_text(
                '🖼 <b>По исходному изображению</b>\n\n' + esc(answer)
            )
        except Exception as exc:
            await ctx.errors.record(request_id, message.from_user.id, 'image_followup', exc)
            # Fall back to the normal stored-material Q&A instead of failing the
            # whole interaction if Telegram cannot re-download the image or the
            # selected provider temporarily rejects vision.
            try:
                await progress.delete()
            except Exception:
                pass
            raise SkipHandler

    return router
