from dataclasses import dataclass
from datetime import datetime, timedelta

from app.services.copilot import build_inbox, detect_copilot_command, rank_materials


@dataclass
class MaterialStub:
    id: int
    title: str
    summary: str
    extracted_text: str
    created_at: datetime
    type: str = 'text'


@dataclass
class ReminderStub:
    text: str
    remind_at: datetime
    status: str = 'active'


def test_detect_memory_search_command():
    command = detect_copilot_command('Найди в памяти где было про оплату поставщику')
    assert command is not None
    assert command.kind == 'memory_search'
    assert 'оплату' in command.value.lower()


def test_detect_project_command():
    command = detect_copilot_command('Создай проект Поставщик Альфа')
    assert command is not None
    assert command.kind == 'create_project'
    assert command.value == 'Поставщик Альфа'


def test_rank_materials_understands_related_payment_words():
    now = datetime.utcnow()
    items = [
        MaterialStub(1, 'Пикник', 'Встреча с друзьями', 'Еда и парк', now),
        MaterialStub(2, 'Договор Альфа', 'Условия поставки', 'Предоплата 50 процентов, платеж до пятницы', now - timedelta(minutes=5)),
    ]
    hits = rank_materials(items, 'где была оплата поставщику?', limit=3)
    assert hits
    assert hits[0].item.id == 2


def test_inbox_extracts_tasks_deadlines_risks_and_reminders():
    now = datetime.utcnow()
    items = [
        MaterialStub(
            1,
            'Договор',
            'Нужно оплатить счет до 25 августа. За просрочку предусмотрен штраф.',
            '',
            now,
        ),
    ]
    reminders = [ReminderStub('Позвонить поставщику', now + timedelta(hours=3))]
    inbox = build_inbox(items, reminders)
    assert inbox['tasks'] >= 1
    assert inbox['deadlines'] >= 2  # one detected date plus one active reminder
    assert inbox['risks'] >= 1
    assert inbox['active_reminders'] == 1
    assert inbox['items']


def test_inbox_ignores_sent_reminder():
    now = datetime.utcnow()
    inbox = build_inbox([], [ReminderStub('Старое', now + timedelta(hours=1), status='sent')])
    assert inbox['active_reminders'] == 0
    assert inbox['deadlines'] == 0
