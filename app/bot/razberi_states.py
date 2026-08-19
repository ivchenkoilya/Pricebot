from aiogram.fsm.state import State, StatesGroup


class MaterialQuestion(StatesGroup):
    waiting = State()


class MaterialReminder(StatesGroup):
    waiting = State()


class WriteForMe(StatesGroup):
    waiting = State()


class CompareMaterials(StatesGroup):
    waiting_ids = State()


class ProjectCreate(StatesGroup):
    waiting_name = State()


class StyleSetup(StatesGroup):
    waiting_profile = State()
