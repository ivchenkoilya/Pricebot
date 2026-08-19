from __future__ import annotations

import uuid

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import Message

from app.ai.conversation import extract_urls, text_without_urls
from app.bot.razberi_helpers import ensure_quota, esc, get_user
from app.bot.razberi_keyboards import actions
from app.processors.text import TextProcessor
from app.services.page_reader import PageReadError


def build_web_router(ctx) -> Router:
    router = Router(name='clarify-web')
    settings = ctx.settings

    @router.message(F.text)
    async def web_link(message: Message):
        value = (message.text or '').strip()
        urls = extract_urls(value)
        if not urls:
            raise SkipHandler

        user = await get_user(ctx, message.from_user)
        if not await ensure_quota(ctx, message, user):
            return

        # One page is handled deeply in a single turn. Extra URLs remain visible
        # to the user and can be sent separately or compared as saved materials.
        url = urls[0]
        instruction = text_without_urls(value)
        progress = await message.answer('🔗 <b>Clarify открывает ссылку…</b>\nЧитаю страницу и отделяю полезное от меню и рекламы')
        request_id = uuid.uuid4().hex
        try:
            page = await ctx.page_reader.read(url)
            source_header = (
                f'Источник URL: {page.final_url}\n'
                f'Заголовок страницы: {page.title or page.host}\n'
                f'Способ чтения: {page.source}\n\n'
            )
            stored_text = source_header + page.text

            if instruction:
                prompt = (
                    f'{instruction}\n\n'
                    'Ответь прямо на задачу пользователя по содержимому страницы. '
                    'Не выдумывай данные, которых на странице нет. '
                    'В конце коротко укажи источник: название страницы и домен.'
                )
                async with ctx.ai_sem:
                    answer, usage = await ctx.ai.ask(prompt, stored_text, model=settings.fast)
                await ctx.usage.record(user.id, settings.fast, 'web_qa', usage)
                material = await ctx.materials.create(
                    user.id,
                    'web',
                    page.title or page.host,
                    stored_text,
                    answer[:4000],
                )
                await ctx.metrics.inc('web_pages_processed', user.id)
                extra = f'\n\n<i>Ещё ссылок в сообщении: {len(urls) - 1}</i>' if len(urls) > 1 else ''
                return await progress.edit_text(
                    f'🔗 <b>{esc(page.title or page.host)}</b>\n\n{esc(answer)}{extra}',
                    reply_markup=actions(material.id, material.type),
                )

            async with ctx.ai_sem:
                result, usage, model = await TextProcessor(ctx.ai).process(stored_text, 'веб-страница')
            await ctx.usage.record(user.id, model, 'web', usage)
            material = await ctx.materials.create(
                user.id,
                'web',
                result.title or page.title or page.host,
                stored_text,
                result.summary,
            )
            await ctx.metrics.inc('web_pages_processed', user.id)
            await progress.edit_text(
                result.to_telegram(f'🔗 <b>Clarify</b> · {esc(page.host)}'),
                reply_markup=actions(material.id, material.type),
            )
        except PageReadError as exc:
            await progress.edit_text(
                '⚠️ Не удалось нормально прочитать эту страницу. Она может требовать вход, CAPTCHA или блокировать автоматическое чтение.\n\n'
                f'<i>{esc(str(exc))}</i>'
            )
        except Exception as exc:
            await ctx.errors.record(request_id, message.from_user.id, 'web', exc)
            await progress.edit_text('⚠️ Не получилось разобрать ссылку. Попробуй ещё раз или пришли скриншот страницы.')

    return router
