import pytest

from app.database.models import User
from app.services.core import MaterialService


@pytest.mark.asyncio
async def test_user_cannot_read_another_users_material(db):
    database, settings = db
    async with database.sessions() as session:
        first = User(telegram_id=100001, first_name='First')
        second = User(telegram_id=100002, first_name='Second')
        session.add_all([first, second])
        await session.commit()
        await session.refresh(first)
        await session.refresh(second)

    materials = MaterialService(database, settings)
    secret = await materials.create(second.id, 'pdf', 'Чужой договор', 'Секретный текст договора')

    assert await materials.get(second.id, secret.id) is not None
    assert await materials.get(first.id, secret.id) is None
    assert await materials.context(first.id, secret.id, 'что в договоре?') == ''


@pytest.mark.asyncio
async def test_material_delete_is_scoped_to_owner(db):
    database, settings = db
    async with database.sessions() as session:
        first = User(telegram_id=100003, first_name='First')
        second = User(telegram_id=100004, first_name='Second')
        session.add_all([first, second])
        await session.commit()
        await session.refresh(first)
        await session.refresh(second)

    materials = MaterialService(database, settings)
    item = await materials.create(second.id, 'text', 'Чужой материал', 'Не удалять')
    assert await materials.delete(first.id, item.id) is False
    assert await materials.get(second.id, item.id) is not None
