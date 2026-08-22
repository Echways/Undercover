import pytest

from undercover.game.engine import (
    MAX_NAME_LENGTH,
    MAX_PLAYERS,
    MIN_PLAYERS,
    GameRulesError,
    max_spies_count,
)
from undercover.game.lobby import (
    cycle_spies_count,
    ensure_playable,
    join,
    leave,
    toggle_category,
    unique_name,
)
from undercover.game.models import LobbyPlayer, LobbyState

CHAT_ID = -1001234567890
HOST_ID = 777


def lobby(players: int = 0) -> LobbyState:
    state = LobbyState(chat_id=CHAT_ID, host_user_id=HOST_ID)
    for number in range(players):
        join(state, LobbyPlayer(user_id=HOST_ID + number, name=f"Игрок-{number}"))
    return state


def test_join_appends_in_arrival_order() -> None:
    state = lobby()

    join(state, LobbyPlayer(user_id=1, name="Аня"))
    join(state, LobbyPlayer(user_id=2, name="Борис"))

    assert [player.name for player in state.players] == ["Аня", "Борис"]


def test_join_refuses_the_same_user_twice() -> None:
    state = lobby()
    join(state, LobbyPlayer(user_id=1, name="Аня"))

    with pytest.raises(GameRulesError):
        join(state, LobbyPlayer(user_id=1, name="Аня"))


def test_join_refuses_the_seventeenth_player() -> None:
    state = lobby(MAX_PLAYERS)

    with pytest.raises(GameRulesError):
        join(state, LobbyPlayer(user_id=-1, name="Лишний"))


def test_leave_removes_the_player_and_keeps_the_rest_in_order() -> None:
    state = lobby(3)

    leave(state, state.players[1].user_id)

    assert [player.name for player in state.players] == ["Игрок-0", "Игрок-2"]


def test_leave_refuses_a_stranger() -> None:
    state = lobby(2)

    with pytest.raises(GameRulesError):
        leave(state, user_id=-1)


def test_leave_clamps_spies_down_to_what_the_smaller_table_allows() -> None:
    state = lobby(6)
    cycle_spies_count(state)

    assert state.spies_count == max_spies_count(6)

    leave(state, state.players[0].user_id)

    assert state.spies_count == max_spies_count(5)


def test_spies_cycle_wraps_at_the_limit() -> None:
    state = lobby(6)
    seen = []
    for _ in range(3):
        cycle_spies_count(state)
        seen.append(state.spies_count)

    assert seen == [2, 1, 2]


def test_spies_cycle_stays_at_one_when_the_table_allows_only_one() -> None:
    state = lobby(MIN_PLAYERS)

    cycle_spies_count(state)

    assert state.spies_count == 1


def test_toggle_category_adds_then_removes() -> None:
    state = lobby()

    toggle_category(state, 7)
    assert state.category_ids == [7]

    toggle_category(state, 7)
    assert state.category_ids == []


def test_ensure_playable_refuses_a_table_of_one() -> None:
    state = lobby(1)

    with pytest.raises(GameRulesError):
        ensure_playable(state)


def test_ensure_playable_passes_the_minimum_table() -> None:
    ensure_playable(lobby(MIN_PLAYERS))


def test_unique_name_leaves_a_free_name_alone() -> None:
    assert unique_name("Аня", taken=["Борис"]) == "Аня"


def test_unique_name_numbers_the_collisions() -> None:
    assert unique_name("Аня", taken=["Аня"]) == "Аня 2"
    assert unique_name("Аня", taken=["Аня", "Аня 2"]) == "Аня 3"


def test_unique_name_keeps_the_result_short_enough_for_a_card() -> None:
    long_name = "Ы" * MAX_NAME_LENGTH

    result = unique_name(long_name, taken=[long_name])

    assert len(result) <= MAX_NAME_LENGTH
    assert result != long_name


def test_unique_name_trims_an_overlong_name_even_without_a_collision() -> None:
    assert len(unique_name("Ы" * 100, taken=[])) == MAX_NAME_LENGTH
