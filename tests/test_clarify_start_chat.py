import pytest

from app.ai.intent import classify_text_intent, looks_like_followup
from app.bot.clarify_start import ABOUT_TEXT, CAPABILITIES_TEXT, START_TEXT, _start_keyboard
from app.bot.razberi_keyboards import actions
from app.services.conversation_context import ConversationContextService
from app.services.core import MaterialService


def test_brand_chat_intents_are_not_new_materials():
    assert classify_text_intent('Привет').name == 'greeting'
    assert classify_text_intent('Кто ты?').name == 'about'
    assert classify_text_intent('Что ты умеешь?').name == 'capabilities'
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
    assert looks_like_followup('А какой там срок?') is True
    assert looks_like_followup('В какой маске этот человек') is True
    decision = classify_text_intent('В какой маске этот человек', has_recent_material=False)
    assert decision.name == 'new_material'
    assert decision.uses_recent_material is False


@pytest.mark.asyncio
async def test_clear_hides_old_material_but_keeps_history(db):
    database, settings = db
    materials = MaterialService(database, settings)
    conversations = ConversationContextService(database, materials, settings)

    old = await materials.create(1, 'text', 'Старый материал', 'Срок — пятница', 'Срок — пятница')
    assert [item.id for item in await conversations.recent_materials(1, 3)] == [old.id]

    conversations.remember(1, 'user', 'А какой срок?')
    await conversations.clear(1)
    assert await conversations.recent_materials(1, 3) == []
    assert conversations.history_text(1) == ''

    new = await materials.create(1, 'text', 'Новый материал', 'Оплата завтра', 'Оплата завтра')
    assert [item.id for item in await conversations.recent_materials(1, 3)] == [new.id]
