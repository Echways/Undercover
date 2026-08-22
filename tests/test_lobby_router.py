from collections.abc import AsyncIterator
from datetime import timedelta
from functools import partial
from typing import Final

import pytest
from aiogram import Dispatcher
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage, SendPhoto

from fake_bot import CHAT_ID, HOST_ID, FakeSession, make_bot, message_update
from fake_games import FakeGameStateRepository
from fake_lobbies import FakeLobbyRepository
from fake_words import FakeWords, catalog, pizza
from lobby_harness import Group
from undercover.bot.routers.discussion import start_discussion
from undercover.bot.routers.lobby import create_lobby_router
from undercover.bot.turn_clock import TurnClock, TurnKeeper
from undercover.game.models import (
    DEFAULT_TURN_SECONDS,
    GameMode,
    GameSessionState,
    GameStatus,
    LobbyView,
    PlayerState,
)
from undercover.texts import Buttons, Errors, Lobby
from undercover.utils.keyed_locks import KeyedLocks

IDLE_TICK: Final = timedelta(minutes=1)
GUEST_ID: Final = 555
OTHER_ID: Final = 666


@pytest.fixture
def words() -> FakeWords:
    return FakeWords(pizza(), categories=catalog("Еда", "Города"))


@pytest.fixture
async def group(words: FakeWords) -> AsyncIterator[Group]:
    session = FakeSession()
    games = FakeGameStateRepository()
    lobbies = FakeLobbyRepository()
    keeper = TurnKeeper(clock=TurnClock(tick=IDLE_TICK), locks=KeyedLocks())
    dispatcher = Dispatcher(games=games, lobbies=lobbies)
    dispatcher.include_router(
        create_lobby_router(words.open, partial(start_discussion, keeper=keeper))
    )

    yield Group(
        dispatcher=dispatcher,
        bot=make_bot(session),
        session=session,
        games=games,
        lobbies=lobbies,
        words=words,
    )

    await keeper.clock.shutdown()


def running_game() -> GameSessionState:
    return GameSessionState(
        session_id="already-running",
        chat_id=CHAT_ID,
        host_user_id=HOST_ID,
        status=GameStatus.DISCUSSION,
        players=[PlayerState(order_index=0, name="Аня", is_spy=True)],
        word_id=1,
        word_text="пицца",
    )


def replies(group: Group) -> list[str | None]:
    return [call.text for call in group.session.calls(SendMessage)]


async def test_game_opens_a_lobby_with_the_sender_as_host(group: Group) -> None:
    await group.command("/undercover")

    assert group.lobbies.stored.host_user_id == HOST_ID
    assert group.screen.texts[0] == Buttons.JOIN_LOBBY


async def test_game_refuses_while_a_game_is_running_in_the_chat(group: Group) -> None:
    await group.games.save(running_game())

    await group.command("/undercover")

    assert group.lobbies.is_empty
    assert Errors.GAME_IN_CHAT in replies(group)


async def test_game_reopens_an_existing_lobby_without_losing_the_roster(group: Group) -> None:
    await group.command("/undercover")
    await group.press(Buttons.JOIN_LOBBY, user_id=GUEST_ID)

    await group.command("/undercover")

    assert [player.user_id for player in group.lobbies.stored.players] == [GUEST_ID]


async def test_joining_pings_the_private_chat_and_shows_the_name_in_the_roster(
    group: Group,
) -> None:
    await group.command("/undercover")

    await group.press(Buttons.JOIN_LOBBY, user_id=GUEST_ID)

    assert Lobby.DM_WELCOME in replies(group)
    assert len(group.lobbies.stored.players) == 1


async def test_a_closed_private_chat_redirects_to_the_deep_link_instead_of_joining(
    group: Group,
) -> None:
    await group.command("/undercover")
    group.session.failures[SendMessage] = TelegramForbiddenError(
        method=SendMessage(chat_id=GUEST_ID, text="x"),
        message="bot can't initiate conversation with a user",
    )

    await group.press(Buttons.JOIN_LOBBY, user_id=GUEST_ID)

    assert group.lobbies.stored.players == []
    assert any(url and f"start=join_{CHAT_ID}" in url for url in group.redirects)


async def test_joining_twice_is_refused_without_a_second_ping(group: Group) -> None:
    await group.command("/undercover")
    await group.press(Buttons.JOIN_LOBBY, user_id=GUEST_ID)
    pings = len(group.session.calls(SendMessage))

    await group.press(Buttons.JOIN_LOBBY, user_id=GUEST_ID)

    assert Lobby.ALREADY_IN in group.alerts
    assert len(group.session.calls(SendMessage)) == pings


async def test_two_players_with_the_same_telegram_name_get_told_apart(group: Group) -> None:
    await group.command("/undercover")

    await group.press(Buttons.JOIN_LOBBY, user_id=GUEST_ID)
    await group.press(Buttons.JOIN_LOBBY, user_id=OTHER_ID)

    names = [player.name for player in group.lobbies.stored.players]
    assert len(names) == 2
    assert len(set(names)) == 2


async def test_leaving_removes_the_player(group: Group) -> None:
    await group.command("/undercover")
    await group.press(Buttons.JOIN_LOBBY, user_id=GUEST_ID)

    await group.press(Buttons.LEAVE_LOBBY, user_id=GUEST_ID)

    assert group.lobbies.stored.players == []


async def test_leaving_when_never_joined_says_so(group: Group) -> None:
    await group.command("/undercover")

    await group.press(Buttons.LEAVE_LOBBY, user_id=GUEST_ID)

    assert Lobby.NOT_IN in group.alerts


async def test_a_button_from_a_closed_lobby_says_it_is_closed(group: Group) -> None:
    await group.command("/undercover")
    data = group.screen.callback_data(Buttons.JOIN_LOBBY)
    await group.lobbies.delete(CHAT_ID)

    await group.tap(data, user_id=GUEST_ID)

    assert Errors.LOBBY_CLOSED in group.alerts


async def test_game_in_a_private_chat_points_to_a_group(group: Group) -> None:
    await group.dispatcher.feed_update(
        group.bot, message_update("/undercover", chat_id=HOST_ID, chat_type="private")
    )

    assert Errors.GROUP_ONLY in replies(group)


async def joined(group: Group, *user_ids: int) -> None:
    await group.command("/undercover")
    for user_id in user_ids:
        await group.press(Buttons.JOIN_LOBBY, user_id=user_id)


async def test_the_spies_button_walks_the_allowed_range_and_wraps(group: Group) -> None:
    await joined(group, *range(100, 106))

    await group.press(Buttons.SPIES_COUNT.format(count=1))
    assert group.lobbies.stored.spies_count == 2

    await group.press(Buttons.SPIES_COUNT.format(count=2))
    assert group.lobbies.stored.spies_count == 1


async def test_only_the_host_changes_the_settings(group: Group) -> None:
    await group.command("/undercover")

    await group.press(Buttons.SPIES_COUNT.format(count=1), user_id=GUEST_ID)

    assert group.lobbies.stored.spies_count == 1
    assert Errors.NOT_HOST in group.alerts


async def test_categories_open_toggle_and_close(group: Group) -> None:
    await group.command("/undercover")

    await group.press(Buttons.CHANGE_CATEGORIES)
    opened: LobbyView = group.lobbies.stored.view
    assert opened is LobbyView.CATEGORIES

    await group.press(Lobby.CATEGORY_FREE.format(title="Еда"))
    assert group.lobbies.stored.category_ids == [1]

    await group.press(Lobby.CATEGORY_CHOSEN.format(title="Еда"))
    assert group.lobbies.stored.category_ids == []

    await group.press(Buttons.CATEGORIES_DONE)
    closed: LobbyView = group.lobbies.stored.view
    assert closed is LobbyView.ROSTER


async def test_a_category_button_from_a_stranger_changes_nothing(group: Group) -> None:
    await group.command("/undercover")
    await group.press(Buttons.CHANGE_CATEGORIES)
    data = group.screen.callback_data(Lobby.CATEGORY_FREE.format(title="Еда"))

    await group.tap(data, user_id=GUEST_ID)

    assert group.lobbies.stored.category_ids == []
    assert Errors.NOT_HOST in group.alerts


async def test_a_started_game_hands_out_roles_and_opens_the_first_turn(group: Group) -> None:
    await joined(group, GUEST_ID, OTHER_ID)

    await group.press(Buttons.PLAY)

    state = group.games.stored
    assert state.mode is GameMode.GROUP
    assert sorted(player.user_id or 0 for player in state.players) == [GUEST_ID, OTHER_ID]
    assert {call.chat_id for call in group.session.calls(SendPhoto)} >= {GUEST_ID, OTHER_ID}
    assert group.lobbies.is_empty
    assert Lobby.STARTED in [screen.text for screen in group.screens]


async def test_the_first_turn_lands_in_the_group_chat(group: Group) -> None:
    await joined(group, GUEST_ID, OTHER_ID)

    await group.press(Buttons.PLAY)

    assert CHAT_ID in [call.chat_id for call in group.session.calls(SendPhoto)]
    assert group.games.stored.status is GameStatus.DISCUSSION


async def test_the_lobby_settings_reach_the_session(group: Group) -> None:
    await joined(group, *range(100, 106))
    await group.press(Buttons.SPIES_COUNT.format(count=1))
    await group.press(Buttons.CHANGE_CATEGORIES)
    await group.press(Lobby.CATEGORY_FREE.format(title="Еда"))
    await group.press(Buttons.CATEGORIES_DONE)

    await group.press(Buttons.PLAY)

    state = group.games.stored
    assert sum(player.is_spy for player in state.players) == 2
    assert state.category_ids == [1]


async def test_a_table_of_one_cannot_start(group: Group) -> None:
    await joined(group, GUEST_ID)

    await group.press(Buttons.PLAY)

    assert group.games.is_empty
    assert group.lobbies.stored.players != []


async def test_only_the_host_starts_the_game(group: Group) -> None:
    await joined(group, GUEST_ID, OTHER_ID)

    await group.press(Buttons.PLAY, user_id=GUEST_ID)

    assert group.games.is_empty
    assert Errors.NOT_HOST in group.alerts


async def test_an_undelivered_role_cancels_the_start_and_keeps_the_lobby(group: Group) -> None:
    await joined(group, GUEST_ID, OTHER_ID)
    group.session.failures[SendPhoto] = TelegramForbiddenError(
        method=SendPhoto(chat_id=GUEST_ID, photo="x"), message="bot was blocked by the user"
    )

    await group.press(Buttons.PLAY)

    assert group.games.is_empty
    assert len(group.lobbies.stored.players) == 2
    assert Lobby.DELIVERY_FAILED in group.alerts
    assert any("start=join_" in (text or "") for text in replies(group))


async def test_an_empty_dictionary_stops_the_start_without_losing_the_roster(
    group: Group,
) -> None:
    await joined(group, GUEST_ID, OTHER_ID)
    group.words.word = None

    await group.press(Buttons.PLAY)

    assert group.games.is_empty
    assert len(group.lobbies.stored.players) == 2


async def test_the_chosen_turn_length_reaches_the_session(group: Group) -> None:
    await joined(group, GUEST_ID, OTHER_ID)

    await group.press(Buttons.TURN_LIMIT.format(seconds=DEFAULT_TURN_SECONDS))
    chosen = group.lobbies.stored.turn_seconds
    assert chosen != DEFAULT_TURN_SECONDS

    await group.press(Buttons.PLAY)

    assert group.games.stored.turn_seconds == chosen


async def test_only_the_host_changes_the_turn_length(group: Group) -> None:
    await group.command("/undercover")

    await group.press(Buttons.TURN_LIMIT.format(seconds=DEFAULT_TURN_SECONDS), user_id=GUEST_ID)

    assert group.lobbies.stored.turn_seconds == DEFAULT_TURN_SECONDS
    assert Errors.NOT_HOST in group.alerts
