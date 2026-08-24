from __future__ import annotations

import asyncio

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.razberi_helpers import ensure_quota, esc, get_user
from app.bot.razberi_states import MaterialQuestion


def build_precise_qa_router(ctx) -> Router:
    """Answer explicit material questions before the legacy materials router.

    Retrieval remains local in MaterialService.context. The model receives only
    the selected chunks and is instructed to answer the exact question rather
    than summarising every fact present in neighbouring context.
    """
    router = Router(name='clarify-precise-material-qa')
    settings = ctx.settings

    @router.message(MaterialQuestion.waiting, F.text)
    async def precise_material_question(message: Message, state: FSMContext):
        user = await get_user(ctx, message.from_user)
        data = await state.get_data()
        material_id = data.get('material_id')
        context = await ctx.materials.context(
            user.id,
            int(material_id) if material_id is not None else 0,
            message.text or '',
            limit=max(5, int(settings.retrieval_chunk_limit)),
        )
        if not context:
            await state.clear()
            return await message.answer('Материал не найден.')
        if not await ensure_quota(ctx, message, user):
            return

        task = (
            f'{message.text}\n\n'
            'Ответь ТОЛЬКО на заданный вопрос. Сначала дай прямой ответ. '
            'Не перечисляй другие условия документа, если они не нужны для ответа. '
            'Для простого вопроса используй 1–5 коротких предложений или короткий список. '
            'Если факт привязан к [Страница N], укажи в конце только страницу или страницы, '
            'которые непосредственно подтверждают ответ; не добавляй соседнюю страницу только потому, что она есть в контексте. '
            'Если точного ответа в переданном контексте нет, прямо скажи «В найденных фрагментах точного ответа нет» и ничего не выдумывай.'
        )

        # Direct questions over already indexed chunks do not need the slow smart
        # model by default. Keep them fast and hard-bound the request so the FSM
        # cannot remain stuck for minutes.
        model = settings.fast
        progress = await message.answer('🧠 <b>Ищу точный ответ в документе…</b>')
        try:
            async with ctx.ai_sem:
                answer, usage = await asyncio.wait_for(
                    ctx.ai.ask(task, context, model=model),
                    timeout=20.0,
                )
        except asyncio.TimeoutError:
            await ctx.metrics.inc('material_qa_timeouts', user.id)
            await state.clear()
            return await progress.edit_text(
                '⚠️ <b>Ответ занял слишком много времени</b>\n\n'
                'Я остановил запрос, чтобы бот не зависал. Попробуй задать вопрос ещё раз.'
            )
        except Exception as exc:
            await ctx.errors.record('material-qa', message.from_user.id, 'material_qa', exc)
            await state.clear()
            return await progress.edit_text(
                '⚠️ <b>Не получилось ответить по документу</b>\n\n'
                'Материал сохранён. Попробуй ещё раз через несколько секунд.'
            )

        await ctx.usage.record(user.id, model, 'material_qa', usage)
        await progress.edit_text(esc(answer))
        await state.clear()

    return router
