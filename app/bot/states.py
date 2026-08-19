from aiogram.fsm.state import State, StatesGroup


class TargetPriceState(StatesGroup):
    waiting_price = State()


class AdminUrlState(StatesGroup):
    waiting_url = State()
