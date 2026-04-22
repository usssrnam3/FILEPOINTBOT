from aiogram.fsm.state import State, StatesGroup


class ServiceCheckoutState(StatesGroup):
    waiting_for_comment = State()

