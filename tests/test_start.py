from dataclasses import dataclass
from typing import Final

import pytest
from aiogram import Dispatcher
from aiogram.methods import SendMessage
from aiogram.types import Message
from aiogram_dialog import setup_dialogs
from aiogram_dialog.test_tools import BotClient, MockMessageManager
from aiogram_dialog.test_tools.memory_storage import JsonMemoryStorage

from fake_bot import CHAT_ID, HOST_ID, FakeSession, callback_update, make_bot
from fake_games import FakeGameStateRepository
from fake_words import FakeWords, pizza
from undercover.bot.routers.setup_dialog import create_setup_dialog
from undercover.bot.routers.start import create_start_router
from undercover.texts import Setup as SetupTexts
from undercover.texts import Start

PLAYERS_COUNT: Final = "4"


@dataclass(frozen=True, slots=True)
class Table:
    client: BotClient
    messages: MockMessageManager
    session: FakeSession

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
    dispatcher = Dispatcher(storage=JsonMemoryStorage(), games=FakeGameStateRepository())
    dispatcher.include_router(create_start_router())
    dispatcher.include_router(create_setup_dialog(FakeWords(pizza()).open))
    messages = MockMessageManager()
    setup_dialogs(dispatcher, message_manager=messages)

    return Table(
        client=BotClient(dispatcher, user_id=HOST_ID, chat_id=CHAT_ID, bot=make_bot(session)),
        messages=messages,
        session=session,
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
