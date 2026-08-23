from dataclasses import dataclass
from typing import Final

import pytest
from aiogram import Dispatcher
from aiogram.methods import SendMessage
from aiogram.types import Message
from aiogram_dialog import setup_dialogs
from aiogram_dialog.test_tools import BotClient, MockMessageManager
from aiogram_dialog.test_tools.memory_storage import JsonMemoryStorage

from fake_bot import CHAT_ID, HOST_ID, FakeSession, callback_update, make_bot, message_update
from fake_games import FakeGameStateRepository
from fake_lobbies import FakeLobbyRepository
from fake_words import FakeWords, catalog, pizza
from undercover.bot.routers.reveal import start_reveal
from undercover.bot.routers.setup_dialog import create_setup_dialog
from undercover.bot.routers.start import create_start_router
from undercover.game.models import LobbyState
from undercover.texts import Errors, Lobby, Start
from undercover.texts import Setup as SetupTexts

PLAYERS_COUNT: Final = "4"
GUEST_ID: Final = 555


@dataclass(frozen=True, slots=True)
class Table:
    client: BotClient
    messages: MockMessageManager
    session: FakeSession
    lobbies: FakeLobbyRepository

    async def send(self, text: str) -> None:
        await self.client.send(text)

    @property
    def screen(self) -> Message:
        return self.messages.last_message()

    @property
    def greetings(self) -> list[str | None]:
        return [sent.text for sent in self.session.calls(SendMessage)]


@pytest.fixture
async def table() -> Table:
    session = FakeSession()
    words = FakeWords(pizza(), categories=catalog("Еда", "Города"))
    lobbies = FakeLobbyRepository(LobbyState(chat_id=CHAT_ID, host_user_id=HOST_ID))
    dispatcher = Dispatcher(
        storage=JsonMemoryStorage(), games=FakeGameStateRepository(), lobbies=lobbies
    )
    cached = words.cached()
    dispatcher.include_router(create_start_router(cached))
    dispatcher.include_router(create_setup_dialog(cached, start_reveal))
    messages = MockMessageManager()
    setup_dialogs(dispatcher, message_manager=messages)

    return Table(
        client=BotClient(dispatcher, user_id=HOST_ID, chat_id=CHAT_ID, bot=make_bot(session)),
        messages=messages,
        session=session,
        lobbies=lobbies,
    )


async def deep_link_start(table: Table, payload: str, *, user_id: int = GUEST_ID) -> None:
    await table.client.dp.feed_update(
        table.client.bot,
        message_update(
            f"/start {payload}".strip(),
            user_id=user_id,
            chat_id=user_id,
            chat_type="private",
            update_id=len(table.session.requests) + 1,
        ),
    )


async def test_start_greets_the_table(table: Table) -> None:
    await table.send("/start")

    assert table.greetings == [Start.GREETING]


async def test_the_greeting_carries_the_brand(table: Table) -> None:
    assert "Undercover" in Start.GREETING


async def test_start_opens_the_setup_dialog(table: Table) -> None:
    await table.send("/start")

    assert SetupTexts.ASK_PLAYERS_COUNT in (table.screen.text or "")


async def test_start_restarts_a_setup_left_halfway(table: Table) -> None:
    await table.send("/start")
    await table.send(PLAYERS_COUNT)
    assert SetupTexts.ASK_SPIES_COUNT.split("{")[0] in (table.screen.text or "")

    await table.send("/start")

    assert SetupTexts.ASK_PLAYERS_COUNT in (table.screen.text or "")


async def test_an_ordinary_message_is_not_a_start(table: Table) -> None:
    await table.send("привет")

    assert table.greetings == []


async def test_a_button_press_is_not_a_start(table: Table) -> None:
    await table.client.dp.feed_update(table.client.bot, callback_update("press"))

    assert table.greetings == []


async def test_a_deep_link_start_puts_the_player_into_the_lobby_of_that_chat(
    table: Table,
) -> None:
    await deep_link_start(table, f"join_{CHAT_ID}")

    assert [player.user_id for player in table.lobbies.stored.players] == [GUEST_ID]
    assert Lobby.DM_WELCOME in table.greetings


async def test_a_deep_link_redraws_the_lobby_in_the_group(table: Table) -> None:
    await deep_link_start(table, f"join_{CHAT_ID}")

    assert CHAT_ID in [sent.chat_id for sent in table.session.calls(SendMessage)]


async def test_a_deep_link_to_a_closed_lobby_says_so(table: Table) -> None:
    await table.lobbies.delete(CHAT_ID)

    await deep_link_start(table, f"join_{CHAT_ID}")

    assert Errors.LOBBY_CLOSED in table.greetings


async def test_a_deep_link_from_someone_already_in_the_lobby_does_not_duplicate(
    table: Table,
) -> None:
    await deep_link_start(table, f"join_{CHAT_ID}")

    await deep_link_start(table, f"join_{CHAT_ID}")

    assert len(table.lobbies.stored.players) == 1
    assert Lobby.ALREADY_IN in table.greetings


async def test_a_deep_link_with_junk_does_not_reach_the_lobby_handler(table: Table) -> None:
    await deep_link_start(table, "join_не-число")

    assert table.lobbies.stored.players == []
    assert Start.GREETING in table.greetings


async def test_a_plain_start_still_opens_the_hot_seat_setup(table: Table) -> None:
    await table.send("/start")

    assert Start.GREETING in table.greetings
    assert table.lobbies.stored.players == []
