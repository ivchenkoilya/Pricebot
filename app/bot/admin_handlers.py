from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.bot.keyboards import admin_panel, product_keyboard
from app.bot.states import AdminUrlState
from app.config.settings import Settings
from app.database.models import Notification, PriceHistory, Product, ProviderError, User, Watch
from app.database.session import Database
from app.scheduler.runner import PriceScheduler
from app.services.alerts import evaluate_and_send
from app.services.products import get_or_create_product_from_url, user_is_pro
from app.services.stats import owner_stats
from app.trackers.registry import ProviderRegistry
from app.utils.money import format_money


def is_admin(user_id: int, settings: Settings) -> bool:
    return settings.admin_telegram_id is not None and user_id == settings.admin_telegram_id


def register_admin_handlers(router: Router, settings: Settings, db: Database, registry: ProviderRegistry, scheduler: PriceScheduler, url_re) -> None:
    @router.message(Command('stats'))
    async def stats(message: Message):
        if not is_admin(message.from_user.id, settings):
            return await message.answer('Команда доступна только администратору.')
        async with db.session_factory() as session:
            data = await owner_stats(session)
        await message.answer('<b>PRICE — статистика</b>\n\n' + '\n'.join(f'{k}: {v}' for k, v in data.items()))

    @router.message(Command('test'))
    async def test_panel(message: Message):
        if is_admin(message.from_user.id, settings):
            await message.answer('🧪 <b>TEST PANEL</b>', reply_markup=admin_panel())

    @router.message(Command('refund'))
    async def refund(message: Message, bot: Bot):
        if not is_admin(message.from_user.id, settings):
            return
        parts = (message.text or '').split()
        if len(parts) != 3:
            return await message.answer('Формат: <code>/refund TELEGRAM_ID CHARGE_ID</code>')
        try:
            await bot.refund_star_payment(user_id=int(parts[1]), telegram_payment_charge_id=parts[2])
            await message.answer('✅ Refund запрос отправлен в Telegram.')
        except Exception as exc:
            await message.answer(f'⚠️ Refund не выполнен: {exc.__class__.__name__}')

    @router.callback_query(F.data.startswith('admin:'))
    async def admin_actions(callback: CallbackQuery, state: FSMContext, bot: Bot):
        if not is_admin(callback.from_user.id, settings):
            return await callback.answer('Нет доступа', show_alert=True)
        action = callback.data.split(':', 1)[1]
        if action == 'check_url':
            await state.set_state(AdminUrlState.waiting_url)
            await callback.message.answer('Пришли URL для немедленной проверки.')
        elif action == 'scheduler':
            count = await scheduler.run_once()
            await callback.message.answer(f'✅ Scheduler run завершён. Проверено: {count}')
        elif action in {'test_drop', 'test_alert'}:
            async with db.session_factory() as session:
                user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalar_one_or_none()
                watch = None
                if user:
                    watch = (await session.execute(select(Watch).where(Watch.user_id == user.id, Watch.active.is_(True)).options(selectinload(Watch.product), selectinload(Watch.user)).limit(1))).scalar_one_or_none()
                if not watch or not watch.product.current_price:
                    await callback.message.answer('Сначала добавь и начни отслеживать товар с реальной ценой.')
                else:
                    product = watch.product
                    original = product.current_price
                    test_price = (original * Decimal('0.90')).quantize(Decimal('0.01'))
                    product.current_price = test_price
                    product.last_checked_at = datetime.utcnow()
                    session.add(PriceHistory(product_id=product.id, price=test_price, old_price=original, availability=product.availability, is_test=True))
                    await session.flush()
                    sent = await evaluate_and_send(session, bot, product, original, product.availability, settings)
                    product.current_price = original
                    await session.commit()
                    await callback.message.answer(f'🧪 Тест −10%. Уведомлений: {sent}. Реальная цена восстановлена.')
        elif action == 'products':
            async with db.session_factory() as session:
                rows = (await session.execute(select(Product).order_by(Product.id.desc()).limit(20))).scalars().all()
            await callback.message.answer('\n'.join(f'#{p.id} {p.source} — {p.name[:45]} — {format_money(p.current_price, p.currency)}' for p in rows) or 'Нет товаров')
        elif action == 'watches':
            async with db.session_factory() as session:
                rows = (await session.execute(select(Watch).order_by(Watch.id.desc()).limit(30))).scalars().all()
            await callback.message.answer('\n'.join(f'#{w.id} user={w.user_id} product={w.product_id} active={w.active}' for w in rows) or 'Нет watches')
        elif action == 'errors':
            async with db.session_factory() as session:
                rows = (await session.execute(select(ProviderError).order_by(ProviderError.created_at.desc()).limit(10))).scalars().all()
            await callback.message.answer('\n\n'.join(f'{e.created_at:%d.%m %H:%M} {e.url_host}\n{e.error[:180]}' for e in rows) or 'Ошибок providers нет')
        elif action == 'db':
            await callback.message.answer('🟢 Database: OK' if await db.ping() else '🔴 Database: ERROR')
        elif action == 'clear_me':
            async with db.session_factory() as session:
                user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalar_one_or_none()
                if user:
                    ids = (await session.execute(select(Watch.id).where(Watch.user_id == user.id))).scalars().all()
                    if ids:
                        await session.execute(delete(Notification).where(Notification.watch_id.in_(ids)))
                    await session.execute(delete(Watch).where(Watch.user_id == user.id))
                    await session.commit()
            await callback.message.answer('🧹 Твои тестовые watches очищены.')
        elif action == 'toggle_pro':
            async with db.session_factory() as session:
                user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalar_one_or_none()
                if user:
                    user.is_pro = not user_is_pro(user)
                    user.pro_until = datetime.utcnow() + timedelta(days=30) if user.is_pro else datetime.utcnow()
                    await session.commit()
                    await callback.message.answer(f'👑 TEST PRO: {"ON" if user.is_pro else "OFF"}')
        await callback.answer()

    @router.message(AdminUrlState.waiting_url)
    async def admin_url(message: Message, state: FSMContext):
        if not is_admin(message.from_user.id, settings):
            await state.clear()
            return
        match = url_re.search(message.text or '')
        if not match:
            return await message.answer('Нужна http/https ссылка.')
        async with db.session_factory() as session:
            product, snapshot, error = await get_or_create_product_from_url(session, registry, settings, match.group(0))
        await state.clear()
        text = f'🧪 {product.name}\n{format_money(product.current_price, product.currency)}\nИсточник: {product.source}'
        if error:
            text += f'\n\n<code>{error[:250]}</code>'
        await message.answer(text, reply_markup=product_keyboard(product.id, product.canonical_url))
