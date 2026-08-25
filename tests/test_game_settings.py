import pytest

from undercover.game.settings import (
    DEFAULT_TURN_SECONDS,
    TURN_CHOICES,
    GameSettings,
    Ruleset,
    clamp_spies,
    cycle_spies,
    cycle_turn_seconds,
    max_spies_count,
    toggle_category,
    toggle_ruleset,
)


def test_defaults_are_a_playable_classic_game() -> None:
    settings = GameSettings()

    assert settings.spies_count == 1
    assert settings.turn_seconds == DEFAULT_TURN_SECONDS
    assert settings.ruleset is Ruleset.CLASSIC
    assert settings.category_ids == []


@pytest.mark.parametrize(
    ("players_count", "limit"),
    [(2, 1), (3, 1), (5, 1), (6, 2), (9, 3), (16, 5)],
)
def test_max_spies_count_keeps_civilians_in_majority(players_count: int, limit: int) -> None:
    assert max_spies_count(players_count) == limit


def test_cycle_spies_wraps_at_the_limit() -> None:
    settings = GameSettings()
    seen = []

    for _ in range(4):
        cycle_spies(settings, players_count=9)
        seen.append(settings.spies_count)

    assert seen == [2, 3, 1, 2]


def test_cycle_spies_on_a_small_table_stays_at_one() -> None:
    settings = GameSettings()

    cycle_spies(settings, players_count=2)

    assert settings.spies_count == 1


def test_cycle_turn_seconds_walks_every_choice_and_returns() -> None:
    settings = GameSettings()
    seen = []

    for _ in range(len(TURN_CHOICES)):
        cycle_turn_seconds(settings)
        seen.append(settings.turn_seconds)

    assert sorted(seen) == sorted(TURN_CHOICES)
    assert settings.turn_seconds == DEFAULT_TURN_SECONDS


def test_cycle_turn_seconds_recovers_from_a_value_outside_the_choices() -> None:
    settings = GameSettings(turn_seconds=17)

    cycle_turn_seconds(settings)

    assert settings.turn_seconds == TURN_CHOICES[0]


def test_toggle_ruleset_flips_both_ways() -> None:
    settings = GameSettings()
    seen = []

    for _ in range(2):
        toggle_ruleset(settings)
        seen.append(settings.ruleset)

    assert seen == [Ruleset.SUDDEN_DEATH, Ruleset.CLASSIC]


def test_toggle_category_adds_then_removes_keeping_order() -> None:
    settings = GameSettings()

    toggle_category(settings, 7)
    toggle_category(settings, 3)
    assert settings.category_ids == [7, 3]

    toggle_category(settings, 7)
    assert settings.category_ids == [3]


def test_clamp_spies_lowers_the_count_when_the_table_shrinks() -> None:
    settings = GameSettings(spies_count=3)

    clamp_spies(settings, players_count=4)

    assert settings.spies_count == 1


def test_clamp_spies_leaves_a_fitting_count_alone() -> None:
    settings = GameSettings(spies_count=2)

    clamp_spies(settings, players_count=9)

    assert settings.spies_count == 2
