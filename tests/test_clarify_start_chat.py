import pytest

from app.ai.intent import classify_text_intent, looks_like_followup
from app.bot.clarify_start import ABOUT_TEXT, CAPABILITIES_TEXT, START_TEXT, _start_keyboard
from app.bot.razberi_keyboards import actions
from app.database.models import User
from app.services.conversation_context import ConversationContextService
from app.services.core import MaterialService


async def _create_users(database, count: int = 1) -> list[int]:
    async with database.sessions() as session:
        users = [
            User(telegram_id=90_000 + index, username=f'user{index}', first_name=f'User {index}')
            for index in range(count)
        ]
        session.add_all(users)
        await session.commit()
        return [user.id for user in users]


def test_brand_chat_intents_are_not_new_materials():
    assert classify_text_intent('Привет').name == 'greeting'
    assert classify_text_intent('Кто ты?').name == 'about'
    assert classify_text_intent('Что ты умеешь?').name == 'capabilities'
    assert classify_text_intent('Список команд').name == 'capabilities'
    assert 'Привет! Я Clarify' in START_TEXT
    assert 'Я Clarify' in ABOUT_TEXT
    assert 'Возможности Clarify' in CAPABILITIES_TEXT
    assert '/start' in CAPABILITIES_TEXT
    assert '/summary' in CAPABILITIES_TEXT
    assert '/clear' in CAPABILITIES_TEXT


def test_start_keyboard_contains_requested_actions():
    keyboard = _start_keyboard('')
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert '✨ Что умеет Clarify' in labels
    assert '💡 Примеры' in labels
    assert '❓ Помощь' in labels
    assert '🧠 Как это работает' in labels
    assert '🗑 Очистить контекст' in labels


def test_material_actions_offer_followup_tools():
    keyboard = actions(7, 'pdf')
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert '⚡ Кратко' in labels
    assert '📌 Главное' in labels
    assert '🧠 Простыми словами' in labels
    assert '✅ Что делать' in labels
    assert '⚠️ Риски' in labels
    assert '❓ Задать вопрос' in labels


def test_missing_context_shape_is_detectable_without_breaking_legacy_router():
    assert looks_like_followup('А какой срок?') is True
    assert looks_like_followup('А какой там срок?') is True
    assert looks_like_followup('В какой маске этот человек') is True
    decision = classify_text_intent('В какой маске этот человек', has_recent_material=False)
    assert decision.name == 'new_material'
    assert decision.uses_recent_material is False


@pytest.mark.asyncio
async def test_clear_hides_old_material_but_keeps_history(db):
    database, settings = db
    [user_id] = await _create_users(database)
    materials = MaterialService(database, settings)
    conversations = ConversationContextService(database, materials, settings)

    old = await materials.create(user_id, 'text', 'Старый материал', 'Срок — пятница', 'Срок — пятница')
    assert [item.id for item in await conversations.recent_materials(user_id, 3)] == [old.id]

    conversations.remember(user_id, 'user', 'А какой срок?')
    await conversations.clear(user_id)
    assert await conversations.recent_materials(user_id, 3) == []
    assert conversations.history_text(user_id) == ''

    new = await materials.create(user_id, 'text', 'Новый материал', 'Оплата завтра', 'Оплата завтра')
    assert [item.id for item in await conversations.recent_materials(user_id, 3)] == [new.id]


@pytest.mark.asyncio
async def test_context_is_isolated_between_users_and_new_material_resets_turns(db):
    database, settings = db
    first_id, second_id = await _create_users(database, 2)
    materials = MaterialService(database, settings)
    conversations = ConversationContextService(database, materials, settings)

    first_old = await materials.create(first_id, 'text', 'Первый', 'Текст первого', 'Первый')
    second = await materials.create(second_id, 'text', 'Второй', 'Текст второго', 'Второй')
    assert [item.id for item in await conversations.recent_materials(first_id, 3)] == [first_old.id]
    assert [item.id for item in await conversations.recent_materials(second_id, 3)] == [second.id]

    conversations.remember(first_id, 'assistant', 'Старый ответ первого пользователя')
    first_new = await materials.create(first_id, 'text', 'Новая тема', 'Новая тема', 'Новая тема')
    assert [item.id for item in await conversations.recent_materials(first_id, 3)][0] == first_new.id
    assert conversations.history_text(first_id) == ''
    assert [item.id for item in await conversations.recent_materials(second_id, 3)] == [second.id]

    await conversations.clear(first_id)
    assert await conversations.recent_materials(first_id, 3) == []
    assert [item.id for item in await conversations.recent_materials(second_id, 3)] == [second.id]
