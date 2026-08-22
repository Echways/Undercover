import asyncio

import pytest

from undercover.utils.keyed_locks import KeyedLocks


async def test_the_same_key_runs_one_at_a_time() -> None:
    locks = KeyedLocks()
    trace: list[str] = []

    async def worker(name: str) -> None:
        async with locks.held("game"):
            trace.append(f"{name}-in")
            await asyncio.sleep(0)
            trace.append(f"{name}-out")

    await asyncio.gather(worker("a"), worker("b"))

    assert trace in (
        ["a-in", "a-out", "b-in", "b-out"],
        ["b-in", "b-out", "a-in", "a-out"],
    )


async def test_different_keys_do_not_wait_for_each_other() -> None:
    locks = KeyedLocks()
    entered = asyncio.Event()

    async def holder() -> None:
        async with locks.held("first"):
            entered.set()
            await asyncio.sleep(0.05)

    async def passer() -> None:
        await entered.wait()
        async with locks.held("second"):
            return

    await asyncio.wait_for(asyncio.gather(holder(), passer()), timeout=1)


async def test_a_finished_key_is_forgotten_so_the_registry_does_not_grow() -> None:
    locks = KeyedLocks()

    async with locks.held("game"):
        assert locks.busy_keys == frozenset({"game"})

    assert locks.busy_keys == frozenset()


async def test_a_raising_block_still_releases_the_key() -> None:
    locks = KeyedLocks()

    with pytest.raises(RuntimeError):
        async with locks.held("game"):
            raise RuntimeError("бум")

    assert locks.busy_keys == frozenset()
    async with locks.held("game"):
        pass


async def test_everyone_waiting_on_a_key_shares_one_lock() -> None:
    locks = KeyedLocks()
    inside = 0
    seen: list[int] = []

    async def worker() -> None:
        nonlocal inside
        async with locks.held("game"):
            inside += 1
            seen.append(inside)
            await asyncio.sleep(0)
            inside -= 1

    await asyncio.gather(*(worker() for _ in range(5)))

    assert seen == [1] * 5
    assert locks.busy_keys == frozenset()
