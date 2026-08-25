import pytest

from undercover.game.engine import (
    MAX_NAME_LENGTH,
    MAX_PLAYERS,
    MIN_PLAYERS,
    GameRulesError,
    max_spies_count,
)
from undercover.game.lobby import ensure_playable, join, leave, unique_name
from undercover.game.models import (
    DEFAULT_TURN_SECONDS,
    TURN_CHOICES,
    LobbyPlayer,
    LobbyState,
    Ruleset,
)
from undercover.game.rules import Rule
from undercover.game.settings import (
    cycle_spies,
    cycle_turn_seconds,
    toggle_category,
    toggle_ruleset,
)

CHAT_ID = -1001234567890
HOST_ID = 777


def lobby(players: int = 0, **overrides: object) -> LobbyState:
    state = LobbyState.model_validate({"chat_id": CHAT_ID, "host_user_id": HOST_ID} | overrides)
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

    with pytest.raises(GameRulesError) as refusal:
        join(state, LobbyPlayer(user_id=1, name="Аня"))

    assert refusal.value.rule is Rule.ALREADY_SEATED


def test_join_refuses_the_seventeenth_player() -> None:
    state = lobby(MAX_PLAYERS)

    with pytest.raises(GameRulesError) as refusal:
        join(state, LobbyPlayer(user_id=-1, name="Лишний"))

    assert refusal.value.rule is Rule.LOBBY_FULL


def test_leave_removes_the_player_and_keeps_the_rest_in_order() -> None:
    state = lobby(3)

    leave(state, state.players[1].user_id)

    assert [player.name for player in state.players] == ["Игрок-0", "Игрок-2"]


def test_leave_refuses_a_stranger() -> None:
    state = lobby(2)

    with pytest.raises(GameRulesError) as refusal:
        leave(state, user_id=-1)

    assert refusal.value.rule is Rule.NOT_SEATED


def test_leave_clamps_spies_down_to_what_the_smaller_table_allows() -> None:
    state = lobby(6)
    cycle_spies(state.settings, len(state.players))

    assert state.settings.spies_count == max_spies_count(6)

    leave(state, state.players[0].user_id)

    assert state.settings.spies_count == max_spies_count(5)


def test_spies_cycle_wraps_at_the_limit() -> None:
    state = lobby(6)
    seen = []
    for _ in range(3):
        cycle_spies(state.settings, len(state.players))
        seen.append(state.settings.spies_count)

    assert seen == [2, 1, 2]


def test_spies_cycle_stays_at_one_when_the_table_allows_only_one() -> None:
    state = lobby(MIN_PLAYERS)

    cycle_spies(state.settings, len(state.players))

    assert state.settings.spies_count == 1


def test_toggle_category_adds_then_removes() -> None:
    state = lobby()

    toggle_category(state.settings, 7)
    assert state.settings.category_ids == [7]

    toggle_category(state.settings, 7)
    assert state.settings.category_ids == []


def test_ensure_playable_refuses_a_table_of_one() -> None:
    state = lobby(1)

    with pytest.raises(GameRulesError) as refusal:
        ensure_playable(state)

    assert refusal.value.rule is Rule.TOO_FEW_PLAYERS


def test_ensure_playable_passes_the_minimum_table() -> None:
    ensure_playable(lobby(MIN_PLAYERS))


def test_ensure_playable_refuses_a_table_its_host_never_joined() -> None:
    state = lobby(MIN_PLAYERS, host_user_id=HOST_ID - 1)

    with pytest.raises(GameRulesError) as refusal:
        ensure_playable(state)

    assert refusal.value.rule is Rule.HOST_MUST_PLAY


def test_unique_name_leaves_a_free_name_alone() -> None:
    assert unique_name("Аня", taken=["Борис"]) == "Аня"


def test_unique_name_gives_up_when_every_suffix_is_taken() -> None:
    crowd = ["Аня", *(f"Аня {number}" for number in range(2, MAX_PLAYERS + 2))]

    with pytest.raises(GameRulesError) as refusal:
        unique_name("Аня", taken=crowd)

    assert refusal.value.rule is Rule.NAME_CLASH


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


def test_a_new_lobby_starts_at_the_default_turn_length() -> None:
    assert lobby().settings.turn_seconds == DEFAULT_TURN_SECONDS


def test_the_turn_length_walks_every_choice_and_comes_back() -> None:
    state = lobby()
    seen = []
    for _ in range(len(TURN_CHOICES)):
        cycle_turn_seconds(state.settings)
        seen.append(state.settings.turn_seconds)

    assert sorted(seen) == sorted(TURN_CHOICES)
    assert state.settings.turn_seconds == DEFAULT_TURN_SECONDS


def test_an_unknown_turn_length_falls_back_to_the_first_choice() -> None:
    state = lobby(settings={"turn_seconds": 999})

    cycle_turn_seconds(state.settings)

    assert state.settings.turn_seconds == TURN_CHOICES[0]


def test_a_new_lobby_plays_by_the_classic_rules() -> None:
    assert lobby().settings.ruleset is Ruleset.CLASSIC


def test_the_ruleset_switches_there_and_back() -> None:
    state = lobby()
    seen = []
    for _ in range(2):
        toggle_ruleset(state.settings)
        seen.append(state.settings.ruleset)

    assert seen == [Ruleset.SUDDEN_DEATH, Ruleset.CLASSIC]


def test_lobby_carries_settings_as_one_object() -> None:
    state = lobby()

    assert state.settings.spies_count == 1
    assert state.settings.ruleset is Ruleset.CLASSIC


def test_ensure_playable_clamps_spies_to_the_shrunken_table() -> None:
    state = lobby(9)
    state.settings.spies_count = 3

    for player in list(state.players[4:]):
        leave(state, player.user_id)
    ensure_playable(state)

    assert state.settings.spies_count == 1
