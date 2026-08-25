from datetime import timedelta
from typing import Final

from redis.asyncio import Redis

from undercover.game.models import LobbyState

__all__ = ["LOBBY_KEY_PREFIX", "LOBBY_TTL", "LOBBY_VERSION", "LobbyRepository", "LobbyState"]

LOBBY_TTL: Final = timedelta(hours=6)

LOBBY_VERSION: Final = "v1"

LOBBY_KEY_PREFIX: Final = f"lobby:{LOBBY_VERSION}:"


class LobbyRepository:
    def __init__(self, redis: Redis, ttl: timedelta = LOBBY_TTL) -> None:
        self._redis = redis
        self._ttl = ttl

    async def save(self, lobby: LobbyState) -> None:
        await self._redis.set(_lobby_key(lobby.chat_id), lobby.model_dump_json(), ex=self._ttl)

    async def load(self, chat_id: int) -> LobbyState | None:
        raw = await self._redis.get(_lobby_key(chat_id))
        return None if raw is None else LobbyState.model_validate_json(raw)

    async def delete(self, chat_id: int) -> None:
        await self._redis.delete(_lobby_key(chat_id))


def _lobby_key(chat_id: int) -> str:
    return f"{LOBBY_KEY_PREFIX}{chat_id}"
