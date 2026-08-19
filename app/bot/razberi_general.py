from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.razberi_helpers import ensure_quota, esc, get_user
from app.bot.razberi_keyboards import actions, delete_data_confirm, draft_actions, main_menu, pro_button, reminder_confirm
from app.bot.razberi_states import WriteForMe
from app.processors.text import TextProcessor
from app.services.core import is_active_pro
from app.services.reminders import parse_reminder


def build_general_router(ctx) -> Router:
    router = Router(name='razberi-general')
    settings = ctx.settings

    @router.message(CommandStart())
    async def start(message: Message):
        user = await get_user(ctx, message.from_user)
        await ctx.metrics.inc('starts', user.id)
        await message.answer(
            '👋 <b>Я РАЗБЕРИ</b>\n\n'
            'Просто отправь мне что-нибудь:\n'
            '🎤 голосовое\n📄 документ\n📸 скриншот\n📝 текст\n💬 сообщение\n\n'
            'Я сам пойму, что с этим можно сделать.\n\nПопробуй прямо сейчас ↓',
            reply_markup=main_menu(),
        )

    @router.message(Command('help'))
    @router.message(F.text == '❓ Помощь')
    async def help_(message: Message):
        await message.answer(
            'Скинь текст, голосовое, фото, PDF/DOCX/TXT/MD/XLSX/CSV. '
            'После разбора можно спросить по материалу, получить задачи или подготовить ответ.\n\n'
            'Команды: /status /ai_status /delete_my_data /cancel_pro'
        )

    @router.message(F.text == '📎 Разобрать')
    async def unpack(message: Message):
        await message.answer('Отправь сюда текст, голосовое, документ или изображение — я определю тип сам.')

    @router.message(F.text == '🎤 Голосовые')
    async def voices(message: Message):
        await message.answer('Отправь голосовое или аудиофайл. Я расшифрую речь, выделю главное, задачи, суммы и сроки.')

    @router.message(F.text == '📄 Документы')
    async def documents(message: Message):
        await message.answer('Поддерживаются PDF, DOCX, TXT, MD, XLSX и CSV. Просто прикрепи файл.')

    @router.message(F.text == '✍️ Написать')
    async def write(message: Message, state: FSMContext):
        await state.set_state(WriteForMe.waiting)
        await message.answer('✍️ Напиши смысл обычными словами. Например: «поставщику: товар нужен к пятнице, спроси, успеет ли он».')

    @router.message(F.text == '⚙️ Настройки')
    async def settings_view(message: Message):
        user = await get_user(ctx, message.from_user)
        plan = 'PRO' if is_active_pro(user) else 'FREE'
        await message.answer(
            f'⚙️ <b>Настройки</b>\n\nЧасовой пояс: {esc(user.timezone or settings.default_timezone)}\n'
            f'Тариф: {plan}\nAI: {"включён" if settings.ai_enabled else "выключен"}'
        )

    @router.message(Command('status'))
    async def status(message: Message):
        db_ok = await ctx.db.ping()
        if settings.ai_enabled and settings.openai_api_key:
            ai_ok, _, _ = await ctx.ai.status()
        else:
            ai_ok = False
        stt_ok = bool(settings.stt_provider)
        await message.answer(
            f'RAZBERI {settings.version}\n\n'
            f'🟢 Telegram\n'
            f'{"🟢" if db_ok else "🔴"} Database\n'
            f'{"🟢" if ai_ok else "🔴"} AI\n'
            f'🟢 Scheduler\n'
            f'{"🟢" if stt_ok else "🔴"} STT'
        )

    @router.message(Command('ai_status'))
    async def ai_status(message: Message):
        ok, latency, detail = await ctx.ai.status()
        endpoint = ctx.ai.endpoint_label
        if ok:
            await message.answer(
                f'🤖 AI: ON ✅\nEndpoint: {esc(endpoint)}\nModel: {esc(settings.fast)}\nLatency: {latency} sec'
            )
        else:
            await message.answer(
                f'🤖 AI: ERROR ❌\nEndpoint: {esc(endpoint)}\nModel: {esc(settings.fast)}\nПричина: {esc(detail)}'
            )

    @router.message(Command('delete_my_data'))
    async def delete_my_data(message: Message):
        await get_user(ctx, message.from_user)
        await message.answer(
            'Удалить историю материалов, AI-использование и напоминания?\n\n'
            'Финансовые записи платежей останутся для корректного учёта.',
            reply_markup=delete_data_confirm(),
        )

    @router.callback_query(F.data.startswith('privacy:'))
    async def privacy_action(callback: CallbackQuery):
        action = callback.data.split(':', 1)[1]
        if action != 'confirm':
            await callback.message.edit_text('❌ Удаление отменено.')
            return await callback.answer()
        user = await get_user(ctx, callback.from_user)
        await ctx.privacy.delete_user_data(user.id)
        await callback.message.edit_text(
            '🗑 История материалов, AI-использование и напоминания удалены. '
            'Финансовые записи платежей сохранены.'
        )
        await callback.answer()

    @router.message(WriteForMe.waiting, F.text)
    async def write_for_me(message: Message, state: FSMContext):
        user = await get_user(ctx, message.from_user)
        if not await ensure_quota(ctx, message, user):
            return
        progress = await message.answer('✍️ Пишу…')
        try:
            raw, usage = await ctx.ai.compose(message.text)
            await ctx.usage.record(user.id, settings.fast, 'compose', usage)
            material = await ctx.materials.create(user.id, 'draft', 'Черновик сообщения', raw, raw)
            await progress.edit_text('✍️ <b>Готовый текст</b>\n\n' + esc(raw), reply_markup=draft_actions(material.id))
            await state.clear()
        except Exception as exc:
            await ctx.errors.record(uuid.uuid4().hex, message.from_user.id, 'compose', exc)
            await progress.edit_text('⚠️ Не получилось написать текст.')

    @router.callback_query(F.data.startswith('draft:'))
    async def draft_edit(callback: CallbackQuery):
        _, material_id, mode = callback.data.split(':', 2)
        user = await get_user(ctx, callback.from_user)
        material = await ctx.materials.get(user.id, int(material_id))
        if not material:
            return await callback.answer('Черновик не найден', show_alert=True)
        modes = {
            'soft': 'мягче и теплее', 'formal': 'официальнее', 'short': 'максимально короче',
            'humor': 'с лёгким уместным юмором', 'persuasive': 'убедительнее',
            'alternative': 'другой вариант с иной формулировкой',
        }
        raw, usage = await ctx.ai.rewrite(material.extracted_text, modes.get(mode, mode))
        await ctx.usage.record(user.id, settings.fast, 'draft_edit', usage)
        new_material = await ctx.materials.create(user.id, 'draft', 'Вариант сообщения', raw, raw)
        await callback.message.answer('✍️ ' + esc(raw), reply_markup=draft_actions(new_material.id))
        await callback.answer()

    @router.message(F.forward_origin, F.text)
    async def forwarded(message: Message):
        user = await get_user(ctx, message.from_user)
        if not await ensure_quota(ctx, message, user):
            return
        progress = await message.answer('💬 Разбираю пересланное сообщение…')
        try:
            result, usage, model = await ctx.ai.analyze_text(message.text, 'пересланное сообщение')
            await ctx.usage.record(user.id, model, 'forwarded', usage)
            material = await ctx.materials.create(user.id, 'forwarded', result.title, message.text, result.summary)
            from app.bot.razberi_keyboards import forwarded_actions
            await progress.edit_text(result.to_telegram('💬 <b>Сообщение разобрано</b>'), reply_markup=forwarded_actions(material.id))
        except Exception as exc:
            await ctx.errors.record(uuid.uuid4().hex, message.from_user.id, 'forwarded', exc)
            await progress.edit_text('⚠️ Не получилось разобрать сообщение.')

    @router.callback_query(F.data.startswith('fwd:'))
    async def forwarded_reply(callback: CallbackQuery):
        _, material_id, mode = callback.data.split(':', 2)
        user = await get_user(ctx, callback.from_user)
        material = await ctx.materials.get(user.id, int(material_id))
        if not material:
            return await callback.answer('Материал не найден', show_alert=True)
        styles = {'neutral': 'нейтрально', 'friendly': 'дружелюбно', 'short': 'очень коротко', 'humor': 'с лёгким уместным юмором'}
        prompt = f'Подготовь ответ на сообщение в стиле: {styles.get(mode, mode)}. Верни только готовый ответ.'
        raw, usage = await ctx.ai.ask(prompt, material.extracted_text)
        await ctx.usage.record(user.id, settings.smart, 'forward_reply', usage)
        await callback.message.answer('✍️ ' + esc(raw))
        await callback.answer()

    @router.message(F.text)
    async def text(message: Message):
        user = await get_user(ctx, message.from_user)
        text_value = (message.text or '').strip()
        low = text_value.lower()

        if low.startswith('напомни'):
            parsed = parse_reminder(text_value, user.timezone or settings.default_timezone)
            if not parsed:
                return await message.answer('Не понял дату. Пример: «напомни завтра в 10:00 оплатить поставщика».')
            task, when = parsed
            reminder = await ctx.reminders.create_pending(user.id, task, when)
            from datetime import timezone
            from zoneinfo import ZoneInfo
            local = when.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(user.timezone or settings.default_timezone)).strftime('%d.%m.%Y %H:%M')
            return await message.answer(f'⏰ Напомнить:\n<b>{esc(task)}</b>\n\n{local}', reply_markup=reminder_confirm(reminder.id))

        if text_value == '📎 Отправить что-нибудь':
            return await message.answer('Отправь текст, файл, фото или голосовое.')
        if text_value == '👑 PRO':
            return await message.answer(
                f'👑 <b>РАЗБЕРИ PRO</b>\n\n🎤 Длинные голосовые\n📄 Большие документы\n🧠 Полная история\n'
                f'⏰ Напоминания\n🤖 Улучшенный AI\n⚡ Больше обработок\n\n{settings.pro_stars_price} ⭐ / 30 дней',
                reply_markup=pro_button(),
            )
        if not await ensure_quota(ctx, message, user):
            return

        progress = await message.answer('🧠 Разбираю…')
        try:
            latest = await ctx.materials.latest(user.id, 1)
            markers = (
                'а теперь', 'а какие там', 'а сколько', 'а когда', 'что он', 'что она',
                'когда край', 'сколько там', 'есть ли здесь', 'есть ли там', 'ответь ему',
                'ответь ей', 'короче', 'сделай короче',
            )
            recent = latest[0] if latest and latest[0].created_at and datetime.utcnow() - latest[0].created_at < timedelta(hours=6) else None
            if recent and (low.startswith(markers) or low in {'короче', 'ещё короче', 'ответь ему', 'ответь ей'}):
                if 'короч' in low:
                    question = 'Сделай содержание этого материала заметно короче. Верни только краткую версию.'
                elif 'ответь' in low:
                    question = 'Подготовь короткий естественный ответ отправителю на основе материала. Верни только готовый ответ.'
                else:
                    question = text_value
                context = await ctx.materials.context(user.id, recent.id, question)
                answer, usage = await ctx.ai.ask(question, context)
                await ctx.usage.record(user.id, settings.smart, 'context_followup', usage)
                return await progress.edit_text(esc(answer))

            modes = {
                'сократи': 'короче', 'напиши нормально': 'естественно и грамотно',
                'сделай официальнее': 'официально', 'переведи на английский': 'переведи на английский',
                'ответь ему': 'подготовь ответ',
            }
            hit = next((key for key in modes if low.startswith(key + ' ')), None)
            if hit:
                source = text_value[len(hit):].strip()
                raw, usage = await ctx.ai.rewrite(source, modes[hit])
                await ctx.usage.record(user.id, settings.fast, 'rewrite', usage)
                return await progress.edit_text(esc(raw))

            async with ctx.ai_sem:
                result, usage, model = await TextProcessor(ctx.ai).process(text_value)
            await ctx.usage.record(user.id, model, 'text', usage)
            material = await ctx.materials.create(user.id, 'text', result.title, text_value, result.summary)
            await progress.edit_text(result.to_telegram(), reply_markup=actions(material.id))
        except Exception as exc:
            await ctx.errors.record(uuid.uuid4().hex, message.from_user.id, 'text', exc)
            await progress.edit_text('⚠️ AI сейчас не смог обработать запрос. Проверь /ai_status или попробуй позже.')

    return router
