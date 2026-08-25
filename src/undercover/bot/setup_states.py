from aiogram.fsm.state import State, StatesGroup


class Setup(StatesGroup):
    ask_players_count = State()
    ask_player_names = State()
    ask_categories = State()
    confirm_start = State()
