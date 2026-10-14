from aiogram.fsm.state import State, StatesGroup


class AudioEditState(StatesGroup):
    waiting_title = State()
    waiting_artist = State()