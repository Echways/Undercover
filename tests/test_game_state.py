import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from redis.asyncio import Redis

from undercover.game.models import PlayerState
from undercover.redis.game_state import (
    SESSION_TTL,
    GameSessionState,
    GameStateRepository,
    GameStatus,
    _active_game_key,
    _session_key,
)

pytestmark = pytest.mark.integration


def make_state(
    session_id: str = "11111111-1111-1111-1111-111111111111",
    chat_id: int = -1001234567890,
) -> GameSessionState:
    return GameSessionState(
        session_id=session_id,
        chat_id=chat_id,
        host_user_id=777,
        status=GameStatus.DISCUSSION,
        players=[
            PlayerState(order_index=0, name="Аня", is_spy=False, has_viewed=True),
            PlayerState(order_index=1, name="Борис", is_spy=True, card_file_id="AgACAgIAA"),
            PlayerState(order_index=2, name="Вера", is_spy=False),
        ],
        word_id=42,
        word_text="пицца",
        hint_by_spy={1: "её режут на куски"},
        reveal_cursor=3,
        discussion_order=[2, 0, 1],
        discussion_cursor=1,
        current_message_id=555,
        created_at=datetime(2026, 8, 21, 12, 30, 45, 123456, tzinfo=UTC),
    )


async def test_save_then_load_returns_equivalent_state(redis_client: Redis) -> None:
    repository = GameStateRepository(redis_client)
    state = make_state()

    await repository.save(state)

    assert await repository.load(state.session_id) == state


async def test_spy_hint_keys_survive_json_as_integers(redis_client: Redis) -> None:
    repository = GameStateRepository(redis_client)
    await repository.save(make_state())

    loaded = await repository.load(make_state().session_id)

    assert loaded is not None
    assert list(loaded.hint_by_spy) == [1]


async def test_load_returns_none_for_unknown_session(redis_client: Redis) -> None:
    repository = GameStateRepository(redis_client)

    assert await repository.load("no-such-session") is None


async def test_save_sets_six_hour_ttl_on_both_keys(redis_client: Redis) -> None:
    state = make_state()
    await GameStateRepository(redis_client).save(state)

    expected = int(SESSION_TTL.total_seconds())
    session_ttl = await redis_client.ttl(_session_key(state.session_id))
    pointer_ttl = await redis_client.ttl(_active_game_key(state.chat_id))

    assert expected - 5 <= session_ttl <= expected
    assert expected - 5 <= pointer_ttl <= expected


async def test_state_disappears_after_ttl_expires(redis_client: Redis) -> None:
    repository = GameStateRepository(redis_client, ttl=timedelta(seconds=1))
    state = make_state()

    await repository.save(state)
    await asyncio.sleep(1.5)

    assert await repository.load(state.session_id) is None
    assert await repository.load_active(state.chat_id) is None


async def test_active_game_of_chat_is_the_last_saved_one(redis_client: Redis) -> None:
    repository = GameStateRepository(redis_client)
    finished = make_state(session_id="old-session")
    current = make_state(session_id="new-session")

    await repository.save(finished)
    await repository.save(current)

    assert await repository.load_active(current.chat_id) == current


async def test_load_active_returns_none_for_chat_without_game(redis_client: Redis) -> None:
    repository = GameStateRepository(redis_client)

    assert await repository.load_active(-1009999999999) is None


async def test_delete_removes_both_keys(redis_client: Redis) -> None:
    repository = GameStateRepository(redis_client)
    state = make_state()
    await repository.save(state)

    await repository.delete(state.session_id)

    assert await redis_client.exists(_session_key(state.session_id)) == 0
    assert await redis_client.exists(_active_game_key(state.chat_id)) == 0


async def test_delete_keeps_pointer_to_newer_game_of_same_chat(redis_client: Redis) -> None:
    repository = GameStateRepository(redis_client)
    finished = make_state(session_id="old-session")
    current = make_state(session_id="new-session")
    await repository.save(finished)
    await repository.save(current)

    await repository.delete(finished.session_id)

    assert await repository.load(finished.session_id) is None
    assert await repository.load_active(current.chat_id) == current


async def test_delete_of_unknown_session_is_noop(redis_client: Redis) -> None:
    repository = GameStateRepository(redis_client)

    await repository.delete("no-such-session")


async def test_a_session_written_before_the_state_version_is_invisible(
    redis_client: Redis,
) -> None:
    repository = GameStateRepository(redis_client)
    state = make_state()
    legacy = state.model_dump()
    legacy["ballot"] = {"options": ["0", "1"], "votes": {"777": "0"}, "revote": False}

    await redis_client.set(f"game:{state.session_id}", json.dumps(legacy, default=str))
    await redis_client.set(f"chat_active_game:{state.chat_id}", state.session_id)

    assert await repository.load(state.session_id) is None
    assert await repository.load_active(state.chat_id) is None
