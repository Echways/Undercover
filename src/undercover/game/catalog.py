from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from datetime import timedelta
from time import monotonic
from typing import Final

from undercover.game.engine import Catalog, CatalogFactory, CategoryRecord

CATEGORIES_TTL: Final = timedelta(minutes=5)


class CachedCatalog:
    def __init__(
        self,
        open_catalog: CatalogFactory,
        ttl: timedelta = CATEGORIES_TTL,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._open_catalog = open_catalog
        self._ttl = ttl.total_seconds()
        self._clock = clock
        self._categories: Sequence[CategoryRecord] | None = None
        self._read_at = 0.0

    def open(self) -> AbstractAsyncContextManager[Catalog]:
        return self._open_catalog()

    async def categories(self) -> Sequence[CategoryRecord]:
        now = self._clock()
        if self._categories is None or now - self._read_at >= self._ttl:
            async with self._open_catalog() as catalog:
                self._categories = await catalog.list_playable_categories()
            self._read_at = now
        return self._categories
