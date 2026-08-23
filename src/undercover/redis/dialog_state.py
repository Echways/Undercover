from typing import Final

from aiogram.fsm.storage.base import DefaultKeyBuilder
from redis.asyncio import Redis

__all__ = ["DIALOG_KEYS", "DialogStateRepository"]

DIALOG_KEYS: Final = DefaultKeyBuilder(with_destiny=True)

SCAN_BATCH: Final = 100


class DialogStateRepository:
    def __init__(self, redis: Redis, keys: DefaultKeyBuilder = DIALOG_KEYS) -> None:
        self._redis = redis
        self._prefix = f"{keys.prefix}{keys.separator}"
        self._separator = keys.separator

    async def count(self, chat_id: int) -> int:
        return len(await self._keys(chat_id))

    async def clear(self, chat_id: int) -> None:
        keys = await self._keys(chat_id)
        if keys:
            await self._redis.delete(*keys)

    async def _keys(self, chat_id: int) -> list[str]:
        pattern = f"{self._prefix}{chat_id}{self._separator}*"
        return [key async for key in self._redis.scan_iter(match=pattern, count=SCAN_BATCH)]
