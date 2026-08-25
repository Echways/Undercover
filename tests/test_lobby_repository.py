import pytest
from redis.asyncio import Redis

from undercover.game.models import GameSettings, LobbyPlayer, LobbyState, LobbyView
from undercover.redis.lobby_state import LOBBY_KEY_PREFIX, LobbyRepository

pytestmark = pytest.mark.integration

CHAT_ID = -1001234567890


def lobby() -> LobbyState:
    return LobbyState(
        chat_id=CHAT_ID,
        host_user_id=777,
        message_id=42,
        players=[LobbyPlayer(user_id=1, name="Аня")],
        settings=GameSettings(spies_count=1, category_ids=[7]),
        view=LobbyView.CATEGORIES,
    )


async def test_saved_lobby_reads_back_field_for_field(redis_client: Redis) -> None:
    repository = LobbyRepository(redis_client)
    saved = lobby()
    await repository.save(saved)

    loaded = await repository.load(CHAT_ID)

    assert loaded == saved


async def test_missing_lobby_is_none(redis_client: Redis) -> None:
    assert await LobbyRepository(redis_client).load(CHAT_ID) is None


async def test_delete_removes_the_lobby(redis_client: Redis) -> None:
    repository = LobbyRepository(redis_client)
    await repository.save(lobby())

    await repository.delete(CHAT_ID)

    assert await repository.load(CHAT_ID) is None


async def test_lobby_key_expires_so_a_forgotten_lobby_does_not_linger(
    redis_client: Redis,
) -> None:
    await LobbyRepository(redis_client).save(lobby())

    assert await redis_client.ttl(f"{LOBBY_KEY_PREFIX}{CHAT_ID}") > 0


def test_lobby_keys_carry_a_version() -> None:
    assert LOBBY_KEY_PREFIX == "lobby:v1:"
