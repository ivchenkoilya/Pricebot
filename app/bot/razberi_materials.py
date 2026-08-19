from __future__ import annotations

from datetime import timezone
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.razberi_helpers import ensure_quota, esc, get_user, send_long_text
from app.bot.razberi_keyboards import actions, materials_list, reminder_confirm
from app.bot.razberi_states import MaterialQuestion, MaterialReminder
from app.services.reminders import parse_reminder


def build_materials_router(ctx) -> Router:
    router = Router(name='razberi-materials')
    settings = ctx.settings

    @router.message(F.text == '🧠 Мои материалы')
    async def materials(message: Message):
        user = await get_user(ctx, message.from_user)
        items = await ctx.materials.latest(user.id, 10)
        if not items:
            return await message.answer('Материалов пока нет. Отправь что-нибудь на разбор.')
        await message.answer(
            '🧠 <b>Последние материалы</b>\n\nНажми на материал, чтобы открыть действия.',
            reply_markup=materials_list(items),
        )

    @router.callback_query(F.data.startswith('matopen:'))
    async def material_open(callback: CallbackQuery):
        user = await get_user(ctx, callback.from_user)
        material_id = int(callback.data.split(':', 1)[1])
        material = await ctx.materials.get(user.id, material_id)
        if not material:
            return await callback.answer('Материал не найден', show_alert=True)
        await callback.message.answer(
            f'🧠 <b>{esc(material.title)}</b>\n\n{esc(material.summary or "Краткое содержание ещё не сохранено.")}',
            reply_markup=actions(material.id),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith('mat:'))
    async def material_action(callback: CallbackQuery, state: FSMContext):
        _, material_id_raw, action = callback.data.split(':', 2)
        material_id = int(material_id_raw)
        user = await get_user(ctx, callback.from_user)
        material = await ctx.materials.get(user.id, material_id)
        if not material:
            return await callback.answer('Материал не найден', show_alert=True)

        if action == 'delete':
            await ctx.materials.delete(user.id, material_id)
            await callback.message.edit_text('🗑 Материал удалён.')
            return await callback.answer()
        if action == 'ask':
            await state.set_state(MaterialQuestion.waiting)
            await state.update_data(material_id=material_id)
            await callback.message.answer('❓ Задай вопрос по этому материалу.')
            return await callback.answer()
        if action == 'remind':
            await state.set_state(MaterialReminder.waiting)
            await state.update_data(material_id=material_id)
            await callback.message.answer(
                '⏰ Напиши, когда и о чём напомнить. Например: «напомни завтра в 10:00 оплатить поставщика».'
            )
            return await callback.answer()
        if action == 'source':
            await send_long_text(callback.message, material.extracted_text or 'Исходный текст не сохранён.')
            return await callback.answer()
        if action == 'summary':
            await callback.message.answer(esc(material.summary or 'Краткое содержание пока не сохранено.'))
            return await callback.answer()

        if not await ctx.usage.allowed(user):
            return await callback.answer('Дневной лимит AI закончился', show_alert=True)

        if action == 'main':
            prompt = 'Перечисли только самое важное краткими пунктами.'
            query = 'самое важное ключевые факты'
            feature = 'material_main'
        elif action == 'tasks':
            prompt = 'Перечисли только задачи/действия. Если задач нет — так и скажи.'
            query = 'задачи сделать нужно действие'
            feature = 'material_tasks'
        elif action == 'reply':
            prompt = 'Подготовь короткий естественный ответ отправителю на основе материала. Верни только готовый ответ.'
            query = 'ответить отправителю'
            feature = 'material_reply'
        else:
            return await callback.answer('Неизвестное действие', show_alert=True)

        context = await ctx.materials.context(user.id, material_id, query)
        answer, usage = await ctx.ai.ask(prompt, context)
        await ctx.usage.record(user.id, settings.smart, feature, usage)
        await callback.message.answer(esc(answer))
        await callback.answer()

    @router.message(MaterialQuestion.waiting, F.text)
    async def material_question(message: Message, state: FSMContext):
        user = await get_user(ctx, message.from_user)
        data = await state.get_data()
        material_id = data.get('material_id')
        context = await ctx.materials.context(user.id, material_id, message.text)
        if not context:
            await state.clear()
            return await message.answer('Материал не найден.')
        if not await ensure_quota(ctx, message, user):
            return
        answer, usage = await ctx.ai.ask(message.text, context)
        await ctx.usage.record(user.id, settings.smart, 'material_qa', usage)
        await message.answer(esc(answer))
        await state.clear()

    @router.message(MaterialReminder.waiting, F.text)
    async def material_reminder(message: Message, state: FSMContext):
        user = await get_user(ctx, message.from_user)
        value = message.text if message.text.lower().startswith('напомни') else 'напомни ' + message.text
        parsed = parse_reminder(value, user.timezone or settings.default_timezone)
        if not parsed:
            return await message.answer('Не понял дату. Пример: «завтра в 10:00 оплатить поставщика».')
        task, when = parsed
        reminder = await ctx.reminders.create_pending(user.id, task, when)
        local = when.replace(tzinfo=timezone.utc).astimezone(
            ZoneInfo(user.timezone or settings.default_timezone)
        ).strftime('%d.%m.%Y %H:%M')
        await state.clear()
        await message.answer(
            f'⏰ Напомнить:\n<b>{esc(task)}</b>\n\n{local}',
            reply_markup=reminder_confirm(reminder.id),
        )

    @router.callback_query(F.data.startswith('rem:'))
    async def reminder_callback(callback: CallbackQuery):
        _, reminder_id_raw, action = callback.data.split(':')
        user = await get_user(ctx, callback.from_user)
        reminder_id = int(reminder_id_raw)
        if action == 'yes':
            reminder = await ctx.reminders.activate(user.id, reminder_id)
            text = '⏰ Напоминание создано.' if reminder else '⚠️ Напоминание не найдено.'
        else:
            await ctx.reminders.cancel(user.id, reminder_id)
            text = '❌ Напоминание отменено.'
        await callback.message.edit_text(text)
        await callback.answer()

    return router
