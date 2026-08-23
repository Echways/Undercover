from datetime import timedelta

import pytest

from fake_words import FakeWords, catalog, pizza
from undercover.game.catalog import CachedCatalog


def make_catalog(words: FakeWords, ttl: timedelta, now: list[float]) -> CachedCatalog:
    return CachedCatalog(words.open, ttl=ttl, clock=lambda: now[0])


async def test_the_first_read_goes_to_the_source() -> None:
    words = FakeWords(pizza(), categories=catalog("Еда", "Города"))
    now = [0.0]

    assert await make_catalog(words, timedelta(minutes=5), now).categories() == words.categories
    assert words.opened == 1


async def test_repeated_reads_within_the_window_are_served_from_memory() -> None:
    words = FakeWords(pizza(), categories=catalog("Еда"))
    now = [0.0]
    cached = make_catalog(words, timedelta(minutes=5), now)

    await cached.categories()
    now[0] = 299.0
    await cached.categories()

    assert words.opened == 1


async def test_the_source_is_asked_again_once_the_window_closes() -> None:
    words = FakeWords(pizza(), categories=catalog("Еда"))
    now = [0.0]
    cached = make_catalog(words, timedelta(minutes=5), now)

    await cached.categories()
    now[0] = 300.0
    await cached.categories()

    assert words.opened == 2


async def test_a_failed_read_is_not_remembered() -> None:
    class Failing(FakeWords):
        async def list_playable_categories(self) -> tuple[()]:
            raise RuntimeError("база недоступна")

    words = Failing(pizza())
    cached = make_catalog(words, timedelta(minutes=5), [0.0])

    with pytest.raises(RuntimeError):
        await cached.categories()
    with pytest.raises(RuntimeError):
        await cached.categories()

    assert words.opened == 2


async def test_the_word_source_is_handed_over_uncached() -> None:
    words = FakeWords(pizza(), categories=catalog("Еда"))
    cached = make_catalog(words, timedelta(minutes=5), [0.0])

    async with cached.open() as source:
        assert await source.get_random_active_word() is words.word

    assert (words.opened, words.closed) == (1, 1)
