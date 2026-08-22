from undercover.game.models import GameSessionState
from undercover.redis.game_state import GameStateRepository


class FakeGameStateRepository(GameStateRepository):
    def __init__(self, *states: GameSessionState) -> None:
        self._states = {state.session_id: state.model_copy(deep=True) for state in states}
        self.saves = 0

    async def load(self, session_id: str) -> GameSessionState | None:
        state = self._states.get(session_id)
        return None if state is None else state.model_copy(deep=True)

    async def load_active(self, chat_id: int) -> GameSessionState | None:
        return next((state for state in self._states.values() if state.chat_id == chat_id), None)

    async def save(self, state: GameSessionState) -> None:
        self._states[state.session_id] = state.model_copy(deep=True)
        self.saves += 1

    async def delete(self, session_id: str) -> None:
        self._states.pop(session_id, None)

    @property
    def is_empty(self) -> bool:
        return not self._states

    @property
    def stored(self) -> GameSessionState:
        (state,) = self._states.values()
        return state
