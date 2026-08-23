import pytest
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from undercover.redis.dialog_state import DIALOG_KEYS, DialogStateRepository

pytestmark = pytest.mark.integration

BOT_ID = 424242
CHAT_ID = -1001234567890
OTHER_CHAT_ID = -1009876543210
HOST_ID = 777
GUEST_ID = 555


def storage(redis_client: Redis) -> RedisStorage:
    return RedisStorage(redis_client, key_builder=DIALOG_KEYS)


def key(chat_id: int, user_id: int, destiny: str = "default") -> StorageKey:
    return StorageKey(bot_id=BOT_ID, chat_id=chat_id, user_id=user_id, destiny=destiny)


async def remember(redis_client: Redis, chat_id: int, user_id: int, destiny: str) -> None:
    await storage(redis_client).set_data(key(chat_id, user_id, destiny), {"step": "имена"})


async def test_a_chat_without_dialogs_counts_none(redis_client: Redis) -> None:
    assert await DialogStateRepository(redis_client).count(CHAT_ID) == 0


async def test_every_dialog_of_the_chat_is_counted(redis_client: Redis) -> None:
    await remember(redis_client, CHAT_ID, HOST_ID, "default")
    await remember(redis_client, CHAT_ID, GUEST_ID, "aiogd:context")

    assert await DialogStateRepository(redis_client).count(CHAT_ID) == 2


async def test_clear_wipes_the_dialogs_of_the_whole_chat(redis_client: Redis) -> None:
    repository = DialogStateRepository(redis_client)
    await remember(redis_client, CHAT_ID, HOST_ID, "default")
    await remember(redis_client, CHAT_ID, GUEST_ID, "aiogd:context")

    await repository.clear(CHAT_ID)

    assert await repository.count(CHAT_ID) == 0
    assert await storage(redis_client).get_data(key(CHAT_ID, HOST_ID)) == {}


async def test_a_neighbouring_chat_keeps_its_dialogs(redis_client: Redis) -> None:
    repository = DialogStateRepository(redis_client)
    await remember(redis_client, CHAT_ID, HOST_ID, "default")
    await remember(redis_client, OTHER_CHAT_ID, HOST_ID, "default")

    await repository.clear(CHAT_ID)

    assert await repository.count(OTHER_CHAT_ID) == 1


async def test_clearing_an_idle_chat_touches_nothing(redis_client: Redis) -> None:
    await DialogStateRepository(redis_client).clear(CHAT_ID)

    assert await redis_client.dbsize() == 0
