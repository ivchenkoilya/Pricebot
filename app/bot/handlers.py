from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, PreCheckoutQuery
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.bot.admin_handlers import is_admin, register_admin_handlers
from app.bot.keyboards import main_menu, product_keyboard
from app.bot.states import TargetPriceState
from app.config.settings import Settings
from app.database.models import PriceHistory, Product, Subscription, User, Watch
from app.database.session import Database
from app.payments.stars import activate_from_payment, build_pro_payment_keyboard
from app.scheduler.runner import PriceScheduler
from app.services.products import WatchLimitError, create_or_activate_watch, get_or_create_product_from_url, product_stats, user_is_pro
from app.services.users import get_or_create_user, record_metric
from app.trackers.registry import ProviderRegistry
from app.utils.money import format_money, parse_price

URL_RE = re.compile(r'https?://[^\s<>]+', re.I)
_admin = is_admin


def signed(value) -> str:
    return 'нет данных' if value is None else f'{value:+}%'.replace('+0.0%', '0%')


async def card_text(session, product: Product) -> str:
    stats = await product_stats(session, product.id)
    lines = [f'🛍 <b>{product.name}</b>', '', f'<b>{format_money(product.current_price, product.currency)}</b>']
    if stats['change_7d'] is not None:
        lines.append(f'📉 За 7 дней: {signed(stats["change_7d"])}')
    if stats['min'] is not None:
        lines.append(f'🏆 Минимум: {format_money(stats["min"], product.currency)}')
    if product.last_checked_at:
        mins = max(0, int((datetime.utcnow() - product.last_checked_at).total_seconds() // 60))
        lines.extend(['', f'Обновлено: {mins} мин назад'])
    if product.check_status != 'ok':
        lines.extend(['', '⚠️ Источник временно недоступен. Товар сохранён, попробую снова автоматически.'])
    return '\n'.join(lines)


def create_router(settings: Settings, db: Database, registry: ProviderRegistry, scheduler: PriceScheduler) -> Router:
    router = Router(name='price')
    register_admin_handlers(router, settings, db, registry, scheduler, URL_RE)

    @router.message(CommandStart())
    async def start(message: Message):
        async with db.session_factory() as session:
            user = await get_or_create_user(session, message.from_user, settings)
            await record_metric(session, user.id, 'start')
        await message.answer('👋 <b>Я PRICE</b>\n\nПришли мне ссылку на товар.\n\nЯ буду следить за ценой и напишу, когда покупать станет выгоднее.\n\nПопробуй просто скинуть ссылку ↓', reply_markup=main_menu())

    @router.message(Command('id'))
    async def show_id(message: Message):
        await message.answer(f'Твой Telegram ID: <code>{message.from_user.id}</code>')

    @router.message(Command('status'))
    async def status(message: Message):
        async with db.session_factory() as session:
            await get_or_create_user(session, message.from_user, settings)
            products = int((await session.execute(select(func.count(Product.id)))).scalar_one())
            watches = int((await session.execute(select(func.count(Watch.id)).where(Watch.active.is_(True)))).scalar_one())
        db_ok = await db.ping()
        lines = ['<b>PRICE 0.1.0</b>', '', '🟢 Telegram: OK', f'{"🟢" if db_ok else "🔴"} Database: {"OK" if db_ok else "ERROR"}', f'{"🟢" if scheduler.last_error is None else "🟡"} Scheduler: {"OK" if scheduler.last_error is None else "DEGRADED"}', f'{"🟢" if registry.providers else "🔴"} Tracker: {"OK" if registry.providers else "ERROR"}', f'📦 Products: {products}', f'🔔 Watches: {watches}']
        if is_admin(message.from_user.id, settings):
            lines += ['', f'TEST_MODE={settings.test_mode}', f'Last scheduler run={scheduler.last_run_at or "—"}', f'Last error={scheduler.last_error or "—"}']
        await message.answer('\n'.join(lines))

    @router.message(Command('paysupport'))
    async def paysupport(message: Message):
        async with db.session_factory() as session:
            user = await get_or_create_user(session, message.from_user, settings)
            sub = (await session.execute(select(Subscription).where(Subscription.user_id == user.id).order_by(Subscription.started_at.desc()).limit(1))).scalar_one_or_none()
        if sub:
            await message.answer(f'💳 Последний payment ID: <code>{sub.telegram_payment_charge_id}</code>\nПередай его администратору PRICE, если нужен refund или помощь.')
        else:
            await message.answer('💳 Платежей Stars пока не записано. Если оплата прошла, но PRO не включился, пришли администратору скрин и свой /id.')

    @router.message(Command('cancelpro'))
    async def cancelpro(message: Message, bot: Bot):
        async with db.session_factory() as session:
            user = await get_or_create_user(session, message.from_user, settings)
            sub = (await session.execute(select(Subscription).where(Subscription.user_id == user.id, Subscription.status == 'active').order_by(Subscription.started_at.desc()).limit(1))).scalar_one_or_none()
            if not sub:
                return await message.answer('Активной подписки PRICE PRO нет.')
            try:
                await bot.edit_user_star_subscription(user_id=message.from_user.id, telegram_payment_charge_id=sub.telegram_payment_charge_id, is_canceled=True)
                sub.status = 'canceling'
                await session.commit()
            except Exception as exc:
                return await message.answer(f'⚠️ Не удалось отключить автопродление: {exc.__class__.__name__}')
        await message.answer('✅ Автопродление отключено. PRO действует до конца оплаченного периода.')

    @router.pre_checkout_query()
    async def pre_checkout(query: PreCheckoutQuery):
        ok = query.currency == 'XTR' and query.invoice_payload == 'price_pro_monthly_v1'
        await query.answer(ok=ok, error_message=None if ok else 'Некорректный платёж PRICE.')

    @router.message(F.successful_payment)
    async def payment(message: Message):
        async with db.session_factory() as session:
            user = await get_or_create_user(session, message.from_user, settings)
            sub = await activate_from_payment(session, user, message)
        await message.answer(f'👑 <b>PRICE PRO активирован</b>\nДо: {sub.expires_at:%d.%m.%Y %H:%M}')

    @router.message(F.refunded_payment)
    async def refunded(message: Message):
        refund = message.refunded_payment
        if refund is None:
            return
        async with db.session_factory() as session:
            sub = (await session.execute(select(Subscription).where(Subscription.telegram_payment_charge_id == refund.telegram_payment_charge_id))).scalar_one_or_none()
            if sub:
                sub.status = 'refunded'
                user = await session.get(User, sub.user_id)
                if user:
                    user.is_pro = False
                    user.pro_until = datetime.utcnow()
                await session.commit()
        await message.answer('💳 Возврат Stars зафиксирован.')

    @router.message(F.text == '➕ Добавить')
    async def add_prompt(message: Message):
        await message.answer('Пришли ссылку на товар одним сообщением ↓')

    @router.message(F.text == '🔔 Мои товары')
    async def watches(message: Message):
        async with db.session_factory() as session:
            user = await get_or_create_user(session, message.from_user, settings)
            items = (await session.execute(select(Watch).where(Watch.user_id == user.id, Watch.active.is_(True)).options(selectinload(Watch.product)).order_by(Watch.created_at.desc()))).scalars().all()
        if not items:
            return await message.answer('🔔 Ты пока ни за чем не следишь. Пришли ссылку на товар.')
        lines = [f'🔔 <b>Ты следишь за {len(items)} товарами</b>', '']
        buttons = []
        for w in items[:20]:
            lines.append(f'• {w.product.name[:60]}\n  {format_money(w.product.current_price, w.product.currency)}')
            buttons.append([InlineKeyboardButton(text=w.product.name[:40], callback_data=f'product:{w.product.id}')])
        await message.answer('\n'.join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    @router.message(F.text == '🔥 Снижения')
    async def drops(message: Message):
        async with db.session_factory() as session:
            user = await get_or_create_user(session, message.from_user, settings)
            items = (await session.execute(select(Watch).where(Watch.user_id == user.id, Watch.active.is_(True)).options(selectinload(Watch.product)))).scalars().all()
            found = []
            for w in items:
                rows = (await session.execute(select(PriceHistory.price).where(PriceHistory.product_id == w.product_id, PriceHistory.price.is_not(None), PriceHistory.is_test.is_(False)).order_by(PriceHistory.checked_at.desc()).limit(2))).scalars().all()
                if len(rows) == 2 and rows[0] < rows[1]:
                    pct = ((rows[0] - rows[1]) / rows[1] * Decimal('100')).quantize(Decimal('0.1'))
                    found.append((pct, w.product))
        if not found:
            return await message.answer('🔥 Подтверждённых снижений среди твоих товаров пока нет.')
        await message.answer('🔥 <b>Снижения</b>\n\n' + '\n\n'.join(f'{p.name[:60]}\n📉 {pct}%' for pct, p in sorted(found, key=lambda x: x[0])[:15]))

    @router.message(F.text == '👑 PRO')
    async def pro(message: Message, bot: Bot):
        async with db.session_factory() as session:
            user = await get_or_create_user(session, message.from_user, settings)
            await record_metric(session, user.id, 'pro_opened')
        if user_is_pro(user):
            return await message.answer(f'👑 PRICE PRO активен до {user.pro_until:%d.%m.%Y}' if user.pro_until else '👑 PRICE PRO активен')
        try:
            kb = await build_pro_payment_keyboard(bot, settings)
            await message.answer(f'👑 <b>PRICE PRO</b>\n\nДо {settings.pro_watch_limit} товаров, проверки примерно раз в {settings.check_interval_pro_hours} ч, новый минимум и наличие.\n\nFREE: {settings.free_watch_limit} товара, примерно раз в {settings.check_interval_free_hours} ч.', reply_markup=kb)
        except Exception:
            await message.answer('⚠️ Не удалось создать счёт Stars. Попробуй позже.')

    @router.message(F.text == '⚙️ Настройки')
    async def settings_view(message: Message):
        await message.answer(f'⚙️ Существенное снижение: от {settings.min_drop_percent}%\nCooldown: {settings.alert_cooldown_hours} ч\nЧасовой пояс: {settings.default_timezone}')

    @router.message(F.text == '🔎 Найти дешевле')
    async def cheaper(message: Message):
        await message.answer('🔎 В 0.1.0 я не притворяюсь глобальным поиском. Сравнение работает только для надёжно сопоставленных товаров из уже известных PRICE источников. Пришли ссылку на товар.')

    @router.callback_query(F.data.startswith('product:'))
    async def product_view(callback: CallbackQuery):
        pid = int(callback.data.split(':')[1])
        async with db.session_factory() as session:
            user = await get_or_create_user(session, callback.from_user, settings)
            product = await session.get(Product, pid)
            if not product:
                return await callback.answer('Товар не найден', show_alert=True)
            watch = (await session.execute(select(Watch).where(Watch.user_id == user.id, Watch.product_id == pid, Watch.active.is_(True)))).scalar_one_or_none()
            text = await card_text(session, product)
        await callback.message.answer(text, reply_markup=product_keyboard(pid, product.canonical_url, bool(watch)))
        await callback.answer()

    @router.callback_query(F.data.startswith('follow:'))
    async def follow(callback: CallbackQuery):
        pid = int(callback.data.split(':')[1])
        async with db.session_factory() as session:
            user = await get_or_create_user(session, callback.from_user, settings)
            product = await session.get(Product, pid)
            if not product:
                return await callback.answer('Товар не найден', show_alert=True)
            try:
                await create_or_activate_watch(session, user, product, settings)
                await record_metric(session, user.id, 'watch_created')
            except WatchLimitError as exc:
                await record_metric(session, user.id, 'free_limit_reached')
                return await callback.answer(f'{exc}. Открой 👑 PRO.', show_alert=True)
            interval = settings.check_interval_pro_hours if user_is_pro(user) else settings.check_interval_free_hours
        await callback.message.answer(f'✅ <b>Добавил в наблюдение</b>\nТекущая: {format_money(product.current_price, product.currency)}\nСледующая проверка примерно через {interval} ч.')
        await callback.answer()

    @router.callback_query(F.data.startswith('pause:'))
    async def pause(callback: CallbackQuery):
        pid = int(callback.data.split(':')[1])
        async with db.session_factory() as session:
            user = await get_or_create_user(session, callback.from_user, settings)
            watch = (await session.execute(select(Watch).where(Watch.user_id == user.id, Watch.product_id == pid))).scalar_one_or_none()
            if watch:
                watch.active = False
                await session.commit()
        await callback.answer('Слежение остановлено', show_alert=True)

    @router.callback_query(F.data.startswith('target:'))
    async def target(callback: CallbackQuery, state: FSMContext):
        pid = int(callback.data.split(':')[1])
        async with db.session_factory() as session:
            user = await get_or_create_user(session, callback.from_user, settings)
            product = await session.get(Product, pid)
            if not product:
                return await callback.answer('Товар не найден', show_alert=True)
            try:
                await create_or_activate_watch(session, user, product, settings)
            except WatchLimitError as exc:
                return await callback.answer(str(exc), show_alert=True)
        await state.set_state(TargetPriceState.waiting_price)
        await state.update_data(product_id=pid)
        await callback.message.answer('🎯 Условие: <code>30000</code> или <code>10%</code>')
        await callback.answer()

    @router.message(TargetPriceState.waiting_price)
    async def target_value(message: Message, state: FSMContext):
        raw = (message.text or '').strip()
        pid = int((await state.get_data())['product_id'])
        async with db.session_factory() as session:
            user = await get_or_create_user(session, message.from_user, settings)
            watch = (await session.execute(select(Watch).where(Watch.user_id == user.id, Watch.product_id == pid, Watch.active.is_(True)))).scalar_one_or_none()
            product = await session.get(Product, pid)
            if not watch or not product:
                await state.clear()
                return await message.answer('Товар больше не отслеживается.')
            if raw.endswith('%'):
                try:
                    pct = Decimal(raw[:-1].replace(',', '.'))
                except InvalidOperation:
                    pct = Decimal('-1')
                if pct <= 0 or pct > 90:
                    return await message.answer('Процент от 1 до 90, например <code>10%</code>.')
                watch.target_percent = pct
                if not user_is_pro(user):
                    watch.target_price = None
                await session.commit(); await state.clear()
                return await message.answer(f'🎯 Напишу при снижении минимум на {pct}%.')
            target = parse_price(raw)
            if target is None:
                return await message.answer('Напиши <code>30000</code> или <code>10%</code>.')
            watch.target_price = target
            if not user_is_pro(user):
                watch.target_percent = None
            await session.commit()
        await state.clear()
        await message.answer(f'🎯 Цель: {format_money(target, product.currency)}\nСейчас: {format_money(product.current_price, product.currency)}')

    @router.callback_query(F.data.startswith('newlow:') | F.data.startswith('stock:'))
    async def pro_toggles(callback: CallbackQuery):
        kind, raw = callback.data.split(':', 1); pid = int(raw)
        async with db.session_factory() as session:
            user = await get_or_create_user(session, callback.from_user, settings)
            if not user_is_pro(user):
                return await callback.answer('Доступно в PRICE PRO.', show_alert=True)
            watch = (await session.execute(select(Watch).where(Watch.user_id == user.id, Watch.product_id == pid, Watch.active.is_(True)))).scalar_one_or_none()
            if not watch:
                return await callback.answer('Сначала включи 🔔 Следить.', show_alert=True)
            if kind == 'newlow':
                watch.notify_new_low = not watch.notify_new_low; enabled = watch.notify_new_low
            else:
                watch.notify_in_stock = not watch.notify_in_stock; enabled = watch.notify_in_stock
            await session.commit()
        await callback.answer(f'{"ON" if enabled else "OFF"}', show_alert=True)

    @router.callback_query(F.data.startswith('history:'))
    async def history(callback: CallbackQuery):
        pid = int(callback.data.split(':')[1])
        async with db.session_factory() as session:
            product = await session.get(Product, pid)
            if not product:
                return await callback.answer('Товар не найден', show_alert=True)
            stats = await product_stats(session, pid)
            points = (await session.execute(select(PriceHistory).where(PriceHistory.product_id == pid, PriceHistory.is_test.is_(False)).order_by(PriceHistory.checked_at.desc()).limit(10))).scalars().all()
        lines = [f'📊 <b>{product.name}</b>', '', f'Сейчас: {format_money(stats["current"], product.currency)}', f'Минимум: {format_money(stats["min"], product.currency)}', f'Максимум: {format_money(stats["max"], product.currency)}', f'7 дней: {signed(stats["change_7d"])}', f'30 дней: {signed(stats["change_30d"])}', f'Наблюдаем: {stats["days"]} дн.', '']
        lines += [f'{p.checked_at:%d.%m %H:%M} — {format_money(p.price, product.currency)}' for p in points]
        await callback.message.answer('\n'.join(lines)); await callback.answer()

    @router.message(F.text.regexp(URL_RE))
    async def add_url(message: Message):
        match = URL_RE.search(message.text or '')
        if not match:
            return
        async with db.session_factory() as session:
            user = await get_or_create_user(session, message.from_user, settings)
            await record_metric(session, user.id, 'product_link_sent')
            product, snapshot, _error = await get_or_create_product_from_url(session, registry, settings, match.group(0).rstrip(').,]'))
            text = await card_text(session, product)
        if snapshot:
            await message.answer(text + f'\n\nИсточник: {product.source}', reply_markup=product_keyboard(product.id, product.canonical_url))
        else:
            await message.answer('⚠️ <b>Не смог проверить цену прямо сейчас</b>\n\nТовар сохранён. Я не буду придумывать цену — попробую снова автоматически.', reply_markup=product_keyboard(product.id, product.canonical_url))

    @router.message(F.text)
    async def fallback(message: Message):
        await message.answer('Пришли ссылку на товар — это самый надёжный способ для PRICE 0.1.0.')

    return router
