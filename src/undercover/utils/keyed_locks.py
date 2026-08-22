from asyncio import Lock
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class KeyedLocks:
    def __init__(self) -> None:
        self._locks: dict[str, tuple[Lock, int]] = {}

    @asynccontextmanager
    async def held(self, key: str) -> AsyncIterator[None]:
        lock = self._reserve(key)
        try:
            async with lock:
                yield
        finally:
            self._release(key)

    @property
    def busy_keys(self) -> frozenset[str]:
        return frozenset(self._locks)

    def _reserve(self, key: str) -> Lock:
        lock, waiting = self._locks.get(key, (Lock(), 0))
        self._locks[key] = (lock, waiting + 1)
        return lock

    def _release(self, key: str) -> None:
        lock, waiting = self._locks[key]
        if waiting > 1:
            self._locks[key] = (lock, waiting - 1)
        else:
            del self._locks[key]
