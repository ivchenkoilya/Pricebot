from __future__ import annotations

import re
from datetime import timezone
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.razberi_helpers import ensure_quota, esc, get_user, send_long_text
from app.bot.razberi_keyboards import (
    actions,
    materials_list,
    project_picker,
    projects_list,
    reminder_confirm,
)
from app.bot.razberi_states import CompareMaterials, MaterialQuestion, MaterialReminder, ProjectCreate
from app.services.reminders import parse_reminder


def build_materials_router(ctx) -> Router:
    router = Router(name='clarify-materials')
    settings = ctx.settings

    @router.message(F.text == '🧠 Мои материалы')
    async def materials(message: Message):
        user = await get_user(ctx, message.from_user)
        items = await ctx.materials.latest(user.id, 10)
        if not items:
            return await message.answer('Материалов пока нет. Отправь что-нибудь на разбор.')
        await message.answer(
            '🧠 <b>Мои материалы</b>\n\nНажми на материал — Clarify покажет подходящие действия.',
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
            reply_markup=actions(material.id, material.type),
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
            await callback.message.answer('❓ Задай вопрос по этому материалу. Можно писать естественно: «а оплатить когда?»')
            return await callback.answer()
        if action == 'remind':
            await state.set_state(MaterialReminder.waiting)
            await state.update_data(material_id=material_id)
            await callback.message.answer(
                '⏰ Напиши, когда и о чём напомнить. Например: «завтра в 10:00 оплатить поставщика».'
            )
            return await callback.answer()
        if action == 'source':
            await send_long_text(callback.message, material.extracted_text or 'Исходный текст не сохранён.')
            return await callback.answer()
        if action == 'summary':
            await callback.message.answer('✨ <b>Коротко</b>\n\n' + esc(material.summary or 'Краткое содержание пока не сохранено.'))
            return await callback.answer()
        if action == 'project':
            projects = await ctx.projects.list(user.id)
            if not projects:
                await state.set_state(ProjectCreate.waiting_name)
                await state.update_data(pending_material_id=material_id)
                await callback.message.answer('📁 Проектов пока нет. Напиши название нового проекта.')
            else:
                await callback.message.answer('📁 Выбери проект:', reply_markup=project_picker(material_id, projects))
            return await callback.answer()

        if not await ctx.usage.allowed(user):
            return await callback.answer('Дневной лимит AI закончился', show_alert=True)

        action_map = {
            'main': (
                'Перечисли только самое важное краткими пунктами.',
                'самое важное ключевые факты',
                'material_main',
                settings.fast,
            ),
            'tasks': (
                'Перечисли только задачи и следующие действия. Если задач нет — так и скажи.',
                'задачи сделать нужно действие обязанность',
                'material_tasks',
                settings.fast,
            ),
            'reply': (
                'Подготовь короткий естественный ответ отправителю на основе материала. Верни только готовый ответ.',
                'сообщение просьба вопрос отправитель ответ',
                'material_reply',
                settings.fast,
            ),
            'risks': (
                'Найди риски, штрафы, ограничения, спорные и потенциально невыгодные условия. Для каждого пункта кратко объясни почему это важно. Только факты из материала.',
                'риск штраф пеня неустойка ответственность ограничение обязанность',
                'material_risks',
                settings.smart,
            ),
            'money': (
                'Собери все важные денежные условия: цены, суммы, порядок оплаты, аванс, постоплату, комиссии и денежные штрафы. Укажи контекст каждой суммы.',
                'цена стоимость сумма оплата платеж аванс штраф',
                'material_money',
                settings.fast,
            ),
            'dates': (
                'Собери сроки и даты с пояснением, к чему относится каждый срок. Отдельно отметь крайние сроки.',
                'срок дата дедлайн период дней поставка оплата',
                'material_dates',
                settings.fast,
            ),
            'plain': (
                'Объясни материал простыми словами, как человеку без специальных знаний. Убери канцелярит, но сохрани факты, суммы, сроки и важные ограничения.',
                'главное условия обязанности сумма срок',
                'material_plain',
                settings.fast,
            ),
            'wants': (
                'Скажи максимально конкретно: что от пользователя хотят, что ему нужно сделать, кому ответить, что подтвердить и к какому сроку. Если действия не требуются — скажи это.',
                'требуется нужно сделать обязанность ответ подтвердить срок',
                'material_wants',
                settings.fast,
            ),
        }
        selected = action_map.get(action)
        if not selected:
            return await callback.answer('Неизвестное действие', show_alert=True)
        prompt, query, feature, model = selected
        context = await ctx.materials.context(user.id, material_id, query)
        answer, usage = await ctx.ai.ask(prompt, context, model=model)
        await ctx.usage.record(user.id, model, feature, usage)
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

    @router.message(F.text == '📁 Проекты')
    async def projects(message: Message):
        user = await get_user(ctx, message.from_user)
        items = await ctx.projects.list(user.id)
        if not items:
            await message.answer('📁 Проектов пока нет. Создай первый — внутри можно хранить связанные документы, голосовые и переписки.', reply_markup=projects_list([]))
            return
        await message.answer('📁 <b>Проекты</b>\n\nМатериалы внутри проекта можно анализировать как одну рабочую тему.', reply_markup=projects_list(items))

    @router.callback_query(F.data == 'proj:new')
    async def project_new(callback: CallbackQuery, state: FSMContext):
        await state.set_state(ProjectCreate.waiting_name)
        await state.update_data(pending_material_id=None)
        await callback.message.answer('➕ Напиши название проекта.')
        await callback.answer()

    @router.callback_query(F.data.startswith('projnew:'))
    async def project_new_for_material(callback: CallbackQuery, state: FSMContext):
        material_id = int(callback.data.split(':', 1)[1])
        await state.set_state(ProjectCreate.waiting_name)
        await state.update_data(pending_material_id=material_id)
        await callback.message.answer('➕ Напиши название нового проекта.')
        await callback.answer()

    @router.message(ProjectCreate.waiting_name, F.text)
    async def project_create(message: Message, state: FSMContext):
        user = await get_user(ctx, message.from_user)
        data = await state.get_data()
        project = await ctx.projects.create(user.id, message.text)
        pending_material_id = data.get('pending_material_id')
        if pending_material_id:
            await ctx.projects.add_material(user.id, project.id, int(pending_material_id))
            text = f'📁 <b>{esc(project.name)}</b> создан. Материал добавлен.'
        else:
            text = f'📁 Проект <b>{esc(project.name)}</b> создан.'
        await state.clear()
        await message.answer(text)

    @router.callback_query(F.data.startswith('projadd:'))
    async def project_add(callback: CallbackQuery):
        _, material_raw, project_raw = callback.data.split(':')
        user = await get_user(ctx, callback.from_user)
        ok = await ctx.projects.add_material(user.id, int(project_raw), int(material_raw))
        await callback.answer('Добавлено в проект ✅' if ok else 'Не удалось добавить', show_alert=not ok)

    @router.callback_query(F.data.startswith('projopen:'))
    async def project_open(callback: CallbackQuery):
        user = await get_user(ctx, callback.from_user)
        project_id = int(callback.data.split(':', 1)[1])
        project, items = await ctx.projects.materials(user.id, project_id)
        if not project:
            return await callback.answer('Проект не найден', show_alert=True)
        if not items:
            await callback.message.answer(f'📁 <b>{esc(project.name)}</b>\n\nПока пусто. Добавляй материалы кнопкой «📁 В проект».')
        else:
            await callback.message.answer(
                f'📁 <b>{esc(project.name)}</b>\n\n{len(items)} материалов',
                reply_markup=materials_list(items),
            )
        await callback.answer()

    @router.message(F.text == '🔀 Сравнить')
    async def compare_start(message: Message, state: FSMContext):
        user = await get_user(ctx, message.from_user)
        items = await ctx.materials.latest(user.id, 10)
        if len(items) < 2:
            return await message.answer('Для сравнения нужно хотя бы два материала.')
        await state.set_state(CompareMaterials.waiting_ids)
        await message.answer(
            '🔀 <b>Сравнение материалов</b>\n\nВыбери два номера из списка и пришли их одним сообщением, например: <code>12 15</code>.\n'
            'Clarify сравнит отличия, деньги, сроки, обязательства и риски.',
            reply_markup=materials_list(items),
        )

    @router.message(CompareMaterials.waiting_ids, F.text)
    async def compare_run(message: Message, state: FSMContext):
        user = await get_user(ctx, message.from_user)
        ids = [int(x) for x in re.findall(r'\d+', message.text or '')[:2]]
        if len(ids) != 2 or ids[0] == ids[1]:
            return await message.answer('Нужны два разных номера, например: <code>12 15</code>.')
        first = await ctx.materials.get(user.id, ids[0])
        second = await ctx.materials.get(user.id, ids[1])
        if not first or not second:
            return await message.answer('Один из материалов не найден. Проверь номера.')
        if not await ensure_quota(ctx, message, user):
            return
        progress = await message.answer('🔀 Сравниваю условия…')
        query = 'цена сумма оплата срок дата обязанность риск штраф отличие'
        context_a = await ctx.materials.context(user.id, first.id, query, limit=6)
        context_b = await ctx.materials.context(user.id, second.id, query, limit=6)
        raw, usage = await ctx.ai.compare(first.title, context_a, second.title, context_b)
        await ctx.usage.record(user.id, settings.smart, 'compare_materials', usage)
        await state.clear()
        await progress.edit_text(
            f'🔀 <b>{esc(first.title)}</b> ↔ <b>{esc(second.title)}</b>\n\n{esc(raw)}'
        )

    return router
