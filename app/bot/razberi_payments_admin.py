from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Message, PreCheckoutQuery
from sqlalchemy import func, select

from app.bot.razberi_helpers import esc, get_user
from app.bot.razberi_keyboards import admin_test_keyboard, pro_button
from app.database.models import User
from app.database.razberi_models import AIUsage, ErrorLog, Metric, RazberiPayment, Reminder

SUBSCRIPTION_PERIOD_SECONDS = 2_592_000


def build_payments_admin_router(ctx) -> Router:
    router = Router(name='razberi-payments-admin')
    settings = ctx.settings

    @router.message(F.text == '👑 PRO')
    async def pro(message: Message):
        await ctx.metrics.inc('pro_opened', (await get_user(ctx, message.from_user)).id)
        await message.answer(
            f'👑 <b>РАЗБЕРИ PRO</b>\n\n'
            'Больше возможностей без ежедневных ограничений.\n\n'
            '🎤 Длинные голосовые\n📄 Большие документы\n🧠 История материалов\n'
            '⏰ Напоминания\n🤖 Улучшенный AI\n⚡ Больше обработок\n\n'
            f'{settings.pro_stars_price} ⭐ / 30 дней',
            reply_markup=pro_button(),
        )

    @router.callback_query(F.data == 'pro:buy')
    async def buy(callback: CallbackQuery):
        user = await get_user(ctx, callback.from_user)
        await ctx.metrics.inc('invoice_created', user.id)
        link = await ctx.bot.create_invoice_link(
            title='РАЗБЕРИ PRO',
            description='PRO на 30 дней с автоматическим продлением',
            payload=f'razberi_pro:{user.id}',
            provider_token='',
            currency='XTR',
            prices=[LabeledPrice(label='PRO 30 дней', amount=settings.pro_stars_price)],
            subscription_period=SUBSCRIPTION_PERIOD_SECONDS,
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=f'Оплатить {settings.pro_stars_price} ⭐', url=link)]]
        )
        await callback.message.answer(
            '👑 Подписка PRO на 30 дней с автопродлением. Telegram откроет официальный счёт по кнопке ниже.',
            reply_markup=keyboard,
        )
        await callback.answer()

    @router.pre_checkout_query()
    async def precheckout(query: PreCheckoutQuery):
        payload = query.invoice_payload or ''
        ok = (
            query.currency == 'XTR'
            and payload.startswith('razberi_pro:')
            and query.total_amount == settings.pro_stars_price
        )
        await query.answer(
            ok=ok,
            error_message=None if ok else 'Не удалось проверить платёж. Попробуй ещё раз.',
        )

    @router.message(F.successful_payment)
    async def paid(message: Message):
        user = await get_user(ctx, message.from_user)
        payment = message.successful_payment
        expiration = await ctx.subscriptions.activate(
            user.id,
            payment.telegram_payment_charge_id,
            payment.total_amount,
            getattr(payment, 'subscription_expiration_date', None),
            bool(getattr(payment, 'is_recurring', False)),
        )
        await ctx.metrics.inc('pro_purchased', user.id, payment.total_amount)
        local = expiration.replace(tzinfo=timezone.utc).astimezone(
            ZoneInfo(user.timezone or settings.default_timezone)
        )
        await message.answer(f'👑 PRO активирован до {local.strftime("%d.%m.%Y %H:%M")}. Спасибо!')

    @router.message(F.refunded_payment)
    async def refunded(message: Message):
        payment = message.refunded_payment
        await ctx.subscriptions.mark_refunded(payment.telegram_payment_charge_id)
        await message.answer('↩️ Платёж Telegram Stars отмечен как возвращённый. PRO для этой оплаты отключён.')

    @router.message(Command('cancel_pro'))
    async def cancel_pro(message: Message):
        user = await get_user(ctx, message.from_user)
        subscription = await ctx.subscriptions.latest_active(user.id)
        if not subscription or not subscription.is_recurring:
            return await message.answer('Активной автопродлеваемой подписки PRO не найдено.')
        try:
            await ctx.bot.edit_user_star_subscription(
                user_id=message.from_user.id,
                telegram_payment_charge_id=subscription.telegram_charge_id,
                is_canceled=True,
            )
            await ctx.subscriptions.mark_cancelled(user.id, subscription.telegram_charge_id)
            await message.answer('👑 Автопродление PRO отключено. Доступ останется до конца уже оплаченного периода.')
        except Exception as exc:
            await ctx.errors.record(uuid.uuid4().hex, message.from_user.id, 'cancel_pro', exc)
            await message.answer('⚠️ Не удалось отключить автопродление. Попробуй позже.')

    @router.message(Command('refund'))
    async def refund_admin(message: Message):
        if message.from_user.id != settings.admin_telegram_id:
            return await message.answer('⛔ Нет доступа.')
        parts = (message.text or '').split()
        if len(parts) != 3:
            return await message.answer('Использование: /refund TELEGRAM_ID CHARGE_ID')
        try:
            target = int(parts[1])
            charge = parts[2]
            await ctx.bot.refund_star_payment(user_id=target, telegram_payment_charge_id=charge)
            await ctx.subscriptions.mark_refunded(charge)
            await message.answer('↩️ Refund выполнен и отмечен в БД.')
        except Exception as exc:
            await ctx.errors.record(uuid.uuid4().hex, message.from_user.id, 'refund', exc)
            await message.answer(f'⚠️ Refund не выполнен: {esc(type(exc).__name__)}')

    @router.message(Command('admin'))
    async def admin(message: Message):
        if message.from_user.id != settings.admin_telegram_id:
            return await message.answer('⛔ Нет доступа.')
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        async with ctx.db.sessions() as db:
            users = (await db.execute(select(func.count(User.id)))).scalar_one()
            active = (
                await db.execute(
                    select(func.count(User.id)).where(User.last_active_at >= datetime.utcnow() - timedelta(days=1))
                )
            ).scalar_one()
            pros = (await db.execute(select(func.count(User.id)).where(User.is_pro == True))).scalar_one()
            ai_requests = (
                await db.execute(select(func.count(AIUsage.id)).where(AIUsage.created_at >= today))
            ).scalar_one()
            voice = (
                await db.execute(
                    select(func.coalesce(func.sum(Metric.value), 0)).where(
                        Metric.name == 'voice_processed', Metric.created_at >= today
                    )
                )
            ).scalar_one()
            documents = (
                await db.execute(
                    select(func.coalesce(func.sum(Metric.value), 0)).where(
                        Metric.name == 'documents_processed', Metric.created_at >= today
                    )
                )
            ).scalar_one()
            revenue = (
                await db.execute(
                    select(func.coalesce(func.sum(RazberiPayment.amount), 0)).where(
                        RazberiPayment.created_at >= today, RazberiPayment.status == 'paid'
                    )
                )
            ).scalar_one()
            errors = (
                await db.execute(select(func.count(ErrorLog.id)).where(ErrorLog.created_at >= today))
            ).scalar_one()
        await message.answer(
            f'🛠 <b>РАЗБЕРИ ADMIN</b>\n\n'
            f'👥 Users: {users}\n🟢 Active 24h: {active}\n👑 PRO: {pros}\n'
            f'🤖 AI requests today: {ai_requests}\n🎤 Voice processed: {voice}\n'
            f'📄 Documents processed: {documents}\n💰 Stars revenue: {revenue}\n⚠️ Errors: {errors}'
        )

    @router.message(Command('test'))
    async def test_panel(message: Message):
        if message.from_user.id != settings.admin_telegram_id:
            return await message.answer('⛔ Нет доступа.')
        await message.answer('🧪 <b>RAZBERI test panel</b>', reply_markup=admin_test_keyboard())

    @router.callback_query(F.data.startswith('admtest:'))
    async def admin_test_action(callback: CallbackQuery):
        if callback.from_user.id != settings.admin_telegram_id:
            return await callback.answer('Нет доступа', show_alert=True)
        action = callback.data.split(':', 1)[1]
        if action == 'ai':
            ok, latency, detail = await ctx.ai.status()
            text = f'🤖 AI: {"OK" if ok else "ERROR"} ({latency}s)\n{esc(settings.fast if ok else detail)}'
        elif action == 'db':
            text = '💾 Database: OK' if await ctx.db.ping() else '💾 Database: ERROR'
        elif action == 'stt':
            if settings.stt_provider.lower() in {'smartapi', 'openai', 'remote'}:
                ready = bool(ctx.ai.client)
                text = f'🎤 STT: {esc(settings.stt_provider)}\nAI client: {"OK" if ready else "NOT CONFIGURED"}'
            else:
                ffmpeg = bool(shutil.which('ffmpeg'))
                text = f'🎤 STT: local\nffmpeg: {"OK" if ffmpeg else "NOT FOUND"}\nmodel: {esc(settings.whisper_model)}'
        elif action == 'scheduler':
            async with ctx.db.sessions() as db:
                reminders = (
                    await db.execute(select(func.count()).select_from(Reminder))
                ).scalar_one()
            text = f'⏰ Scheduler service: OK\nReminders in DB: {reminders}'
        elif action == 'usage':
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            async with ctx.db.sessions() as db:
                requests = (await db.execute(select(func.count(AIUsage.id)).where(AIUsage.created_at >= today))).scalar_one()
                input_tokens = (
                    await db.execute(select(func.coalesce(func.sum(AIUsage.input_tokens), 0)).where(AIUsage.created_at >= today))
                ).scalar_one()
                output_tokens = (
                    await db.execute(select(func.coalesce(func.sum(AIUsage.output_tokens), 0)).where(AIUsage.created_at >= today))
                ).scalar_one()
            text = f'📊 Сегодня: {requests} AI запросов\nInput tokens: {input_tokens}\nOutput tokens: {output_tokens}'
        else:
            async with ctx.db.sessions() as db:
                rows = list((await db.execute(select(ErrorLog).order_by(ErrorLog.created_at.desc()).limit(5))).scalars())
            if rows:
                details = []
                for item in rows:
                    reason = (item.message or '').replace('\n', ' ')[:120]
                    details.append(f'{item.created_at:%d.%m %H:%M} {esc(item.feature)} — {esc(item.error_type)}: {esc(reason)}')
                text = '⚠️ Последние ошибки\n' + '\n'.join(details)
            else:
                text = '⚠️ Последние ошибки\nОшибок нет'
        await callback.message.answer(text)
        await callback.answer()

    return router
