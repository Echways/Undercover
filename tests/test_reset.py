from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import GetChatMember, SendMessage
from aiogram.types import InlineKeyboardMarkup

from discussion_harness import SESSION_ID, make_state
from fake_bot import CHAT_ID, HOST_ID, FakeSession, chat_admin, make_bot, message_update
from fake_dialogs import FakeDialogStateRepository
from fake_games import FakeGameStateRepository
from fake_lobbies import FakeLobbyRepository
from undercover.bot.routers.reset import create_reset_router
from undercover.bot.turn_clock import KeyedLocks, Turn, TurnClock, TurnKeeper, TurnView
from undercover.game.models import LobbyPlayer, LobbyState, Seating
from undercover.texts import RESET_COMMAND, Reset

IDLE_TICK = timedelta(minutes=1)
IDLE_VIEW = TurnView(caption="ход", keyboard=InlineKeyboardMarkup(inline_keyboard=[]))
OUTSIDER_ID = HOST_ID + 1
PRIVATE_CHAT_ID = 715450525


@dataclass(frozen=True, slots=True)
class Table:
    dispatcher: Dispatcher
    bot: Bot
    session: FakeSession
    games: FakeGameStateRepository
    lobbies: FakeLobbyRepository
    dialogs: FakeDialogStateRepository
    keeper: TurnKeeper

    async def send(
        self,
        *,
        user_id: int = HOST_ID,
        chat_id: int = CHAT_ID,
        chat_type: str = "supergroup",
    ) -> None:
        await self.dispatcher.feed_update(
            self.bot,
            message_update(
                f"/{RESET_COMMAND}", user_id=user_id, chat_id=chat_id, chat_type=chat_type
            ),
        )

    @property
    def replies(self) -> list[str]:
        return [sent.text for sent in self.session.calls(SendMessage)]


@pytest.fixture
async def table() -> AsyncIterator[Table]:
    session = FakeSession()
    games = FakeGameStateRepository()
    lobbies = FakeLobbyRepository()
    dialogs = FakeDialogStateRepository()
    keeper = TurnKeeper(clock=TurnClock(tick=IDLE_TICK), locks=KeyedLocks())
    dispatcher = Dispatcher(games=games, lobbies=lobbies, dialogs=dialogs)
    dispatcher.include_router(create_reset_router(keeper))

    yield Table(
        dispatcher=dispatcher,
        bot=make_bot(session),
        session=session,
        games=games,
        lobbies=lobbies,
        dialogs=dialogs,
        keeper=keeper,
    )

    await keeper.clock.shutdown()


def lobby(host_user_id: int = HOST_ID) -> LobbyState:
    return LobbyState(
        chat_id=CHAT_ID,
        host_user_id=host_user_id,
        players=[LobbyPlayer(user_id=host_user_id, name="Ведущий")],
    )


async def test_an_idle_chat_has_nothing_to_reset(table: Table) -> None:
    await table.send()

    assert table.replies == [Reset.NOTHING]


async def test_the_host_drops_a_stuck_game(table: Table) -> None:
    await table.games.save(make_state(seating=Seating.GROUP, ids=(HOST_ID, 22, 33, 44)))

    await table.send()

    assert table.games.is_empty
    assert table.replies == [Reset.DONE]


async def test_the_host_drops_a_stuck_lobby(table: Table) -> None:
    await table.lobbies.save(lobby())

    await table.send()

    assert table.lobbies.is_empty
    assert table.replies == [Reset.DONE]


async def test_a_reset_clears_both_the_lobby_and_the_game(table: Table) -> None:
    await table.games.save(make_state(seating=Seating.GROUP))
    await table.lobbies.save(lobby())

    await table.send()

    assert table.games.is_empty
    assert table.lobbies.is_empty


async def test_a_reset_wipes_the_dialogs_left_in_the_chat(table: Table) -> None:
    await table.games.save(make_state(seating=Seating.GROUP))
    table.dialogs.opened_in(CHAT_ID)

    await table.send()

    assert table.dialogs.is_empty


async def test_a_stuck_dialog_alone_is_worth_a_reset(table: Table) -> None:
    table.dialogs.opened_in(CHAT_ID)
    table.session.results[GetChatMember] = [chat_admin(HOST_ID)]

    await table.send()

    assert table.dialogs.is_empty
    assert table.replies == [Reset.DONE]


async def test_a_reset_stops_the_turn_clock(table: Table) -> None:
    state = make_state(seating=Seating.GROUP, turn_seconds=60)
    await table.games.save(state)
    state.turn_deadline = datetime.now(UTC) + timedelta(hours=1)
    table.keeper.clock.start(table.bot, state, IDLE_VIEW, _never_expires)
    assert table.keeper.clock.running == frozenset({SESSION_ID})

    await table.send()

    assert table.keeper.clock.running == frozenset()


async def test_a_bystander_may_not_drop_someone_elses_game(table: Table) -> None:
    await table.games.save(make_state(seating=Seating.GROUP))

    await table.send(user_id=OUTSIDER_ID)

    assert not table.games.is_empty
    assert table.replies == [Reset.DENIED]


async def test_a_chat_admin_may_drop_a_game_they_do_not_host(table: Table) -> None:
    await table.games.save(make_state(seating=Seating.GROUP))
    table.session.results[GetChatMember] = [chat_admin(OUTSIDER_ID)]

    await table.send(user_id=OUTSIDER_ID)

    assert table.games.is_empty
    assert table.replies == [Reset.DONE]


async def test_unreadable_rights_do_not_open_the_reset(table: Table) -> None:
    await table.games.save(make_state(seating=Seating.GROUP))
    table.session.failures[GetChatMember] = TelegramBadRequest(
        method=GetChatMember(chat_id=CHAT_ID, user_id=OUTSIDER_ID), message="user not found"
    )

    await table.send(user_id=OUTSIDER_ID)

    assert not table.games.is_empty
    assert table.replies == [Reset.DENIED]


async def test_a_hot_seat_game_is_reset_by_its_own_host(table: Table) -> None:
    await table.games.save(make_state(chat_id=PRIVATE_CHAT_ID, host_user_id=PRIVATE_CHAT_ID))

    await table.send(user_id=PRIVATE_CHAT_ID, chat_id=PRIVATE_CHAT_ID, chat_type="private")

    assert table.games.is_empty
    assert table.replies == [Reset.DONE]


async def test_a_private_chat_has_no_admins_to_lean_on(table: Table) -> None:
    await table.games.save(make_state(chat_id=PRIVATE_CHAT_ID, host_user_id=PRIVATE_CHAT_ID))

    await table.send(user_id=OUTSIDER_ID, chat_id=PRIVATE_CHAT_ID, chat_type="private")

    assert not table.games.is_empty
    assert table.session.calls(GetChatMember) == []
    assert table.replies == [Reset.DENIED]


async def _never_expires(bot: Bot, turn: Turn) -> None:
    return None
