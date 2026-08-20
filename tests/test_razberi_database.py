from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.database.models import User
from app.services.core import MaterialService, ProjectService, StyleService, UsageService, UserService, is_active_pro
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


@pytest.mark.asyncio
async def test_creator_is_auto_pro_and_bypasses_daily_ai_limit(db):
    database, settings = db
    owner_id = 777001
    settings.admin_telegram_id = owner_id
    settings.free_daily_ai_limit = 1
    settings.pro_daily_ai_limit = 1

    telegram_user = SimpleNamespace(
        id=owner_id,
        username='owner',
        first_name='Owner',
    )
    user = await UserService(database, settings).upsert(telegram_user)
    assert user.is_pro is True
    assert is_active_pro(user) is True

    usage = UsageService(database, settings)
    for _ in range(3):
        await usage.record(user.id, 'fake-model', 'analysis', {'input': 1, 'output': 1})
    assert await usage.ai_count_today(user.id) == 3
    assert await usage.allowed(user) is True


@pytest.mark.asyncio
async def test_projects_keep_existing_material_schema_untouched(db):
    database, settings = db
    async with database.session_factory() as session:
        user = User(telegram_id=912348, first_name='Project Test')
        session.add(user)
        await session.commit()
        await session.refresh(user)

    materials = MaterialService(database, settings)
    projects = ProjectService(database)
    material = await materials.create(user.id, 'pdf', 'Договор', 'Цена 50000 рублей. Срок поставки 5 дней.')
    project = await projects.create(user.id, 'Закупка №42')
    assert await projects.add_material(user.id, project.id, material.id) is True
    loaded_project, items = await projects.materials(user.id, project.id)
    assert loaded_project is not None
    assert loaded_project.name == 'Закупка №42'
    assert [item.id for item in items] == [material.id]


@pytest.mark.asyncio
async def test_user_style_roundtrip(db):
    database, _settings = db
    async with database.session_factory() as session:
        user = User(telegram_id=912349, first_name='Style Test')
        session.add(user)
        await session.commit()
        await session.refresh(user)

    styles = StyleService(database)
    await styles.set(user.id, 'Коротко, разговорно, без канцелярита')
    assert 'разговорно' in await styles.get(user.id)
