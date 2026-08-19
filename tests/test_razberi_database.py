from datetime import datetime, timedelta

import pytest

from app.database.models import User
from app.services.core import MaterialService, UsageService
from app.services.reminders import ReminderService


@pytest.mark.asyncio
async def test_material_and_usage_are_additive(db):
    database, settings = db
    async with database.session_factory() as session:
        user = User(telegram_id=912345, first_name='Test')
        session.add(user)
        await session.commit()
        await session.refresh(user)

    materials = MaterialService(database, settings)
    usage = UsageService(database, settings)
    material = await materials.create(
        user_id=user.id,
        type_='text',
        title='Тестовый материал',
        text='Нужно оплатить 45000 рублей завтра.',
    )
    assert material.id
    loaded = await materials.get(user.id, material.id)
    assert loaded is not None
    assert '45000' in loaded.extracted_text

    await usage.record(user.id, 'fake-model', 'analysis', {'input': 12, 'output': 8})
    assert await usage.ai_count_today(user.id) == 1


@pytest.mark.asyncio
async def test_reminder_survives_database_roundtrip(db):
    database, settings = db
    async with database.session_factory() as session:
        user = User(telegram_id=912346, first_name='Test')
        session.add(user)
        await session.commit()
        await session.refresh(user)

    service = ReminderService(database)
    due_at = datetime.utcnow() - timedelta(seconds=1)
    reminder = await service.create_pending(user.id, 'Проверить заказ', due_at)
    assert reminder.status == 'pending'
    await service.activate(user.id, reminder.id)
    due = await service.due()
    assert any(item.id == reminder.id for item, _telegram_id in due)


@pytest.mark.asyncio
async def test_free_limit_counts_actions(db):
    database, settings = db
    settings.free_daily_ai_limit = 1
    async with database.session_factory() as session:
        user = User(telegram_id=912347, first_name='Test')
        session.add(user)
        await session.commit()
        await session.refresh(user)
    usage = UsageService(database, settings)
    assert await usage.allowed(user) is True
    await usage.record(user.id, 'fake-model', 'analysis', {'input': 1, 'output': 1})
    assert await usage.allowed(user) is False
