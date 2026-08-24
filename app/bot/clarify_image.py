from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import Message

from app.bot.razberi_helpers import ensure_quota, esc, get_user
from app.bot.razberi_keyboards import actions
from app.bot.razberi_media import _material_text_from_result, _optimized_image_payload, _vision_instruction


IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


def build_image_router(ctx) -> Router:
    """Handle photos/image-documents before the generic media fallback."""
    router = Router(name='clarify-image-v2')
    settings = ctx.settings

    async def process_image(message: Message, media, *, extension: str, caption: str, file_name: str = ''):
        user = await get_user(ctx, message.from_user)

        file_unique_id = getattr(media, 'file_unique_id', None)
        cached = await ctx.materials.by_file_unique(user.id, file_unique_id)
        if cached and not caption:
            return await message.answer(
                '♻️ <b>Уже готово</b>\n\n' + esc(cached.summary or cached.title),
                reply_markup=actions(cached.id, cached.type),
            )

        if int(getattr(media, 'file_size', 0) or 0) > settings.max_file_size_mb * 1024 * 1024:
            return await message.answer(f'⚠️ Изображение больше {settings.max_file_size_mb} МБ.')

        if not await ensure_quota(ctx, message, user, feature='vision'):
            return

        request_id = uuid.uuid4().hex
        path = Path(settings.data_dir, 'tmp', request_id + (extension or '.jpg'))
        progress = await message.answer(
            '📸 <b>Clarify смотрит…</b>\nОтвечаю по изображению'
            if caption else
            '📸 <b>Clarify смотрит…</b>\nЧитаю изображение и выделяю главное'
        )

        try:
            loop = asyncio.get_running_loop()
            started = loop.time()
            await ctx.bot.download(media, destination=path)
            download_ms = int((loop.time() - started) * 1000)

            prep_started = loop.time()
            image_b64, image_mime = await asyncio.to_thread(_optimized_image_payload, path, settings)
            prep_ms = int((loop.time() - prep_started) * 1000)

            vision_started = loop.time()
            async with ctx.ai_sem:
                result, usage, model, raw = await ctx.ai.analyze_image(
                    image_b64,
                    image_mime,
                    _vision_instruction(caption),
                )
            vision_ms = int((loop.time() - vision_started) * 1000)
            await ctx.usage.record(user.id, model, 'image_caption' if caption else 'image', usage)

            material = await ctx.materials.create(
                user.id,
                'image',
                result.title or file_name or 'Изображение',
                _material_text_from_result(result, raw, caption),
                result.summary,
                getattr(media, 'file_id', None),
                file_unique_id,
            )
            await ctx.metrics.inc('images_processed', user.id)
            await ctx.metrics.inc('vision_latency_ms', user.id, max(1, vision_ms))
            await ctx.metrics.inc('image_download_latency_ms', user.id, max(1, download_ms))
            await ctx.metrics.inc('image_prepare_latency_ms', user.id, max(1, prep_ms))
            await progress.edit_text(
                result.to_compact_telegram('📸 <b>Clarify</b>'),
                reply_markup=actions(material.id, material.type),
            )
        except Exception as exc:
            await ctx.errors.record(request_id, message.from_user.id, 'image', exc)
            await ctx.metrics.inc('vision_errors', user.id)
            await progress.edit_text(
                '⚠️ Не получилось обработать изображение. Попробуй отправить его ещё раз или как файл JPG/PNG.'
            )
        finally:
            path.unlink(missing_ok=True)

    @router.message(F.photo)
    async def photo(message: Message):
        item = message.photo[-1]
        await process_image(message, item, extension='.jpg', caption=(message.caption or '').strip())

    @router.message(F.document)
    async def image_document(message: Message):
        item = message.document
        extension = Path(item.file_name or '').suffix.lower()
        if extension not in IMAGE_EXTENSIONS:
            raise SkipHandler
        await process_image(
            message,
            item,
            extension=extension,
            caption=(message.caption or '').strip(),
            file_name=item.file_name or '',
        )

    return router
