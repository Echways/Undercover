from undercover.game.models import LobbyState
from undercover.redis.lobby_state import LobbyRepository


class FakeLobbyRepository(LobbyRepository):
    def __init__(self, *lobbies: LobbyState) -> None:
        self._lobbies = {lobby.chat_id: lobby.model_copy(deep=True) for lobby in lobbies}
        self.saves = 0

    async def load(self, chat_id: int) -> LobbyState | None:
        lobby = self._lobbies.get(chat_id)
        return None if lobby is None else lobby.model_copy(deep=True)

    async def save(self, lobby: LobbyState) -> None:
        self._lobbies[lobby.chat_id] = lobby.model_copy(deep=True)
        self.saves += 1

    async def delete(self, chat_id: int) -> None:
        self._lobbies.pop(chat_id, None)

    @property
    def stored(self) -> LobbyState:
        (lobby,) = self._lobbies.values()
        return lobby

    @property
    def is_empty(self) -> bool:
        return not self._lobbies
