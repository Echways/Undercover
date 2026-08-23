from datetime import timedelta
from typing import Final

from redis.asyncio import Redis

from undercover.game.models import GameSessionState, GameStatus

__all__ = ["GameSessionState", "GameStateRepository", "GameStatus"]

SESSION_TTL: Final = timedelta(hours=6)

STATE_VERSION: Final = "v2"

SESSION_KEY_PREFIX: Final = f"game:{STATE_VERSION}:"
ACTIVE_GAME_KEY_PREFIX: Final = f"chat_active_game:{STATE_VERSION}:"


_RELEASE_ACTIVE_GAME: Final = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


class GameStateRepository:
    def __init__(self, redis: Redis, ttl: timedelta = SESSION_TTL) -> None:
        self._redis = redis
        self._ttl = ttl
        self._release_active_game = redis.register_script(_RELEASE_ACTIVE_GAME)

    async def save(self, state: GameSessionState) -> None:
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(_session_key(state.session_id), state.model_dump_json(), ex=self._ttl)
            pipe.set(_active_game_key(state.chat_id), state.session_id, ex=self._ttl)
            await pipe.execute()

    async def load(self, session_id: str) -> GameSessionState | None:
        raw = await self._redis.get(_session_key(session_id))
        return None if raw is None else GameSessionState.model_validate_json(raw)

    async def load_active(self, chat_id: int) -> GameSessionState | None:
        session_id = await self._redis.get(_active_game_key(chat_id))
        return None if session_id is None else await self.load(session_id)

    async def delete(self, session_id: str) -> None:
        state = await self.load(session_id)
        await self._redis.delete(_session_key(session_id))
        if state is not None:
            await self._release_active_game(
                keys=[_active_game_key(state.chat_id)], args=[session_id]
            )


def _session_key(session_id: str) -> str:
    return f"{SESSION_KEY_PREFIX}{session_id}"


def _active_game_key(chat_id: int) -> str:
    return f"{ACTIVE_GAME_KEY_PREFIX}{chat_id}"
