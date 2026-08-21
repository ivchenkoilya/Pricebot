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
from app.services.core import bonus_requests, clarify_plan

SUBSCRIPTION_PERIOD_SECONDS = 2_592_000


def _products(settings) -> dict[str, dict]:
    return {
        'pro': {'kind': 'plan', 'plan': 'PRO', 'price': settings.pro_stars_price, 'title': 'Clarify PRO', 'label': 'PRO · 30 дней'},
        'max': {'kind': 'plan', 'plan': 'MAX', 'price': settings.max_stars_price, 'title': 'Clarify PRO MAX', 'label': 'PRO MAX · 30 дней'},
        'pack100': {'kind': 'pack', 'credits': 100, 'price': settings.request_pack_100_stars, 'title': '+100 запросов'},
        'pack500': {'kind': 'pack', 'credits': 500, 'price': settings.request_pack_500_stars, 'title': '+500 запросов'},
        'pack2000': {'kind': 'pack', 'credits': 2000, 'price': settings.request_pack_2000_stars, 'title': '+2000 запросов'},
    }


def _plans_keyboard(settings) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f'👑 PRO · {settings.pro_stars_price} ⭐', callback_data='plan:buy:pro')],
        [InlineKeyboardButton(text=f'💎 PRO MAX · {settings.max_stars_price} ⭐', callback_data='plan:buy:max')],
        [InlineKeyboardButton(text=f'+100 · {settings.request_pack_100_stars} ⭐', callback_data='plan:buy:pack100'), InlineKeyboardButton(text=f'+500 · {settings.request_pack_500_stars} ⭐', callback_data='plan:buy:pack500')],
        [InlineKeyboardButton(text=f'+2000 запросов · {settings.request_pack_2000_stars} ⭐', callback_data='plan:buy:pack2000')],
    ])


def _plan_text(settings, current: str, bonus: int) -> str:
    return (
        '<b>💳 Тарифы Clarify</b>\n\n'
        f'<b>Сейчас:</b> {esc(current)}' + (f' · +{bonus} доп. запросов' if bonus else '') + '\n\n'
        f'<b>FREE</b> — бесплатно\n'
        f'• {settings.free_daily_ai_limit} AI-запросов в день\n'
        f'• голосовые до {settings.free_voice_max_seconds // 60} минут\n'
        f'• документы до {settings.free_document_max_pages} страниц\n\n'
        f'<b>👑 PRO · {settings.pro_stars_price} ⭐ / 30 дней</b>\n'
        f'• {settings.pro_daily_ai_limit} запросов в день\n'
        f'• голосовые до {settings.pro_voice_max_seconds // 60} минут\n'
        f'• документы до {settings.pro_document_max_pages} страниц\n'
        '• Smart AI режим\n\n'
        f'<b>💎 PRO MAX · {settings.max_stars_price} ⭐ / 30 дней</b>\n'
        f'• {settings.max_daily_ai_limit} запросов в день\n'
        f'• голосовые до {settings.max_voice_max_seconds // 60} минут\n'
        f'• документы до {settings.max_document_max_pages} страниц\n'
        '• максимальные лимиты Clarify\n\n'
        '<b>Нужны только запросы?</b> Докупи пакет — он не сгорает в конце дня и расходуется после дневного лимита.'
    )


async def _invoice(ctx, user, product: str) -> str:
    item = _products(ctx.settings).get(product)
    if not item:
        raise ValueError('unknown product')
    if item['kind'] == 'plan':
        return await ctx.bot.create_invoice_link(
            title=item['title'],
            description=f'{item["title"]} на 30 дней с автоматическим продлением',
            payload=f'clarify_plan:{item["plan"].lower()}:{user.id}',
            provider_token='', currency='XTR',
            prices=[LabeledPrice(label=item['label'], amount=item['price'])],
            subscription_period=SUBSCRIPTION_PERIOD_SECONDS,
        )
    return await ctx.bot.create_invoice_link(
        title=item['title'],
        description=f'{item["credits"]} дополнительных AI-запросов Clarify',
        payload=f'clarify_pack:{item["credits"]}:{user.id}',
        provider_token='', currency='XTR',
        prices=[LabeledPrice(label=item['title'], amount=item['price'])],
    )


def build_payments_admin_router(ctx) -> Router:
    router = Router(name='razberi-payments-admin')
    settings = ctx.settings

    @router.message(F.text.in_({'👑 PRO', '💳 Тарифы'}))
    async def plans(message: Message):
        user = await get_user(ctx, message.from_user)
        await ctx.metrics.inc('pro_opened', user.id)
        await message.answer(_plan_text(settings, clarify_plan(user, settings), bonus_requests(user)), reply_markup=_plans_keyboard(settings))

    @router.callback_query(F.data == 'pro:buy')
    async def buy_legacy(callback: CallbackQuery):
        user = await get_user(ctx, callback.from_user)
        link = await _invoice(ctx, user, 'pro')
        await ctx.metrics.inc('invoice_created', user.id)
        await callback.message.answer('👑 PRO на 30 дней. Telegram откроет официальный счёт.', reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f'Оплатить {settings.pro_stars_price} ⭐', url=link)]]))
        await callback.answer()

    @router.callback_query(F.data.startswith('plan:buy:'))
    async def buy_product(callback: CallbackQuery):
        product = callback.data.split(':', 2)[2]
        user = await get_user(ctx, callback.from_user)
        item = _products(settings).get(product)
        if not item:
            return await callback.answer('Неизвестный продукт', show_alert=True)
        if clarify_plan(user, settings) == 'OWNER' and item['kind'] == 'plan':
            return await callback.answer('OWNER уже имеет Unlimited-доступ', show_alert=True)
        try:
            link = await _invoice(ctx, user, product)
            await ctx.metrics.inc('invoice_created', user.id)
            await callback.message.answer(
                f'💳 <b>{esc(item["title"])}</b>\n\nОплата проходит официально через Telegram Stars.',
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f'Оплатить {item["price"]} ⭐', url=link)]])
            )
            await callback.answer()
        except Exception as exc:
            await ctx.errors.record(uuid.uuid4().hex, callback.from_user.id, 'plan_invoice', exc)
            await callback.answer('Не удалось создать счёт', show_alert=True)

    @router.pre_checkout_query()
    async def precheckout(query: PreCheckoutQuery):
        payload = query.invoice_payload or ''
        ok = False
        if query.currency == 'XTR':
            if payload.startswith('razberi_pro:'):
                ok = query.total_amount == settings.pro_stars_price
            elif payload.startswith('clarify_plan:'):
                parts = payload.split(':')
                if len(parts) == 3:
                    product = 'max' if parts[1] == 'max' else 'pro'
                    ok = query.total_amount == _products(settings)[product]['price']
            elif payload.startswith('clarify_pack:'):
                parts = payload.split(':')
                if len(parts) == 3:
                    try:
                        credits = int(parts[1])
                    except ValueError:
                        credits = 0
                    match = next((x for x in _products(settings).values() if x.get('credits') == credits), None)
                    ok = bool(match and query.total_amount == match['price'])
        await query.answer(ok=ok, error_message=None if ok else 'Не удалось проверить платёж. Попробуй ещё раз.')

    @router.message(F.successful_payment)
    async def paid(message: Message):
        user = await get_user(ctx, message.from_user)
        payment = message.successful_payment
        payload = payment.invoice_payload or ''

        if payload.startswith('clarify_pack:'):
            try:
                credits = int(payload.split(':')[1])
            except (ValueError, IndexError):
                credits = 0
            match = next((x for x in _products(settings).values() if x.get('credits') == credits), None)
            if not match:
                return await message.answer('⚠️ Платёж получен, но пакет не распознан. Напиши в поддержку.')
            total = await ctx.subscriptions.add_request_pack(user.id, payment.telegram_payment_charge_id, payment.total_amount, credits)
            await ctx.metrics.inc('request_pack_purchased', user.id, payment.total_amount)
            return await message.answer(f'✅ Добавлено <b>{credits} запросов</b>. Сейчас в запасе: <b>{total}</b>.')

        plan = 'PRO'
        if payload.startswith('clarify_plan:max:'):
            plan = 'MAX'
        expiration = await ctx.subscriptions.activate(
            user.id,
            payment.telegram_payment_charge_id,
            payment.total_amount,
            getattr(payment, 'subscription_expiration_date', None),
            bool(getattr(payment, 'is_recurring', False)),
            plan=plan,
        )
        await ctx.metrics.inc('pro_purchased', user.id, payment.total_amount)
        local = expiration.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(user.timezone or settings.default_timezone))
        label = 'PRO MAX' if plan == 'MAX' else 'PRO'
        await message.answer(f'✅ <b>{label}</b> активирован до {local.strftime("%d.%m.%Y %H:%M")}. Спасибо!')

    @router.message(F.refunded_payment)
    async def refunded(message: Message):
        payment = message.refunded_payment
        amount = payment.total_amount
        user = await get_user(ctx, message.from_user)
        pack = next((x for x in _products(settings).values() if x.get('kind') == 'pack' and x['price'] == amount), None)
        await ctx.subscriptions.mark_refunded(payment.telegram_payment_charge_id)
        if pack:
            await ctx.subscriptions.remove_request_pack(user.id, pack['credits'])
        await message.answer('↩️ Платёж Telegram Stars отмечен как возвращённый.')

    @router.message(Command('cancel_pro'))
    async def cancel_pro(message: Message):
        user = await get_user(ctx, message.from_user)
        subscription = await ctx.subscriptions.latest_active(user.id)
        if not subscription or not subscription.is_recurring:
            return await message.answer('Активной автопродлеваемой подписки не найдено.')
        try:
            await ctx.bot.edit_user_star_subscription(user_id=message.from_user.id, telegram_payment_charge_id=subscription.telegram_charge_id, is_canceled=True)
            await ctx.subscriptions.mark_cancelled(user.id, subscription.telegram_charge_id)
            await message.answer('✅ Автопродление отключено. Доступ останется до конца оплаченного периода.')
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
            active = (await db.execute(select(func.count(User.id)).where(User.last_active_at >= datetime.utcnow() - timedelta(days=1)))).scalar_one()
            pros = (await db.execute(select(func.count(User.id)).where(User.is_pro == True))).scalar_one()
            ai_requests = (await db.execute(select(func.count(AIUsage.id)).where(AIUsage.created_at >= today))).scalar_one()
            voice = (await db.execute(select(func.coalesce(func.sum(Metric.value), 0)).where(Metric.name == 'voice_processed', Metric.created_at >= today))).scalar_one()
            documents = (await db.execute(select(func.coalesce(func.sum(Metric.value), 0)).where(Metric.name == 'documents_processed', Metric.created_at >= today))).scalar_one()
            revenue = (await db.execute(select(func.coalesce(func.sum(RazberiPayment.amount), 0)).where(RazberiPayment.created_at >= today, RazberiPayment.status == 'paid'))).scalar_one()
            errors = (await db.execute(select(func.count(ErrorLog.id)).where(ErrorLog.created_at >= today))).scalar_one()
        await message.answer(
            f'🛠 <b>Clarify ADMIN</b>\n\n👥 Users: {users}\n🟢 Active 24h: {active}\n👑 Paid plans: {pros}\n'
            f'🤖 AI requests today: {ai_requests}\n🎤 Voice processed: {voice}\n📄 Documents processed: {documents}\n'
            f'💰 Stars revenue: {revenue}\n⚠️ Errors: {errors}'
        )

    @router.message(Command('test'))
    async def test_panel(message: Message):
        if message.from_user.id != settings.admin_telegram_id:
            return await message.answer('⛔ Нет доступа.')
        await message.answer('🧪 <b>Clarify test panel</b>', reply_markup=admin_test_keyboard())

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
                reminders = (await db.execute(select(func.count()).select_from(Reminder))).scalar_one()
            text = f'⏰ Scheduler service: OK\nReminders in DB: {reminders}'
        elif action == 'usage':
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            async with ctx.db.sessions() as db:
                requests = (await db.execute(select(func.count(AIUsage.id)).where(AIUsage.created_at >= today))).scalar_one()
                input_tokens = (await db.execute(select(func.coalesce(func.sum(AIUsage.input_tokens), 0)).where(AIUsage.created_at >= today))).scalar_one()
                output_tokens = (await db.execute(select(func.coalesce(func.sum(AIUsage.output_tokens), 0)).where(AIUsage.created_at >= today))).scalar_one()
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
