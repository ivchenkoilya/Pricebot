from aiogram.fsm.state import State, StatesGroup


class MaterialQuestion(StatesGroup):
    waiting = State()


class MaterialReminder(StatesGroup):
    waiting = State()


class WriteForMe(StatesGroup):
    waiting = State()
