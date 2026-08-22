from random import Random
from typing import Final

import pytest

from undercover.game.engine import MAX_NAME_LENGTH, MAX_PLAYERS
from undercover.game.nicknames import NICKNAMES, pick_nicknames

SEED: Final = 20260822


def rng() -> Random:
    return Random(SEED)


def test_the_pool_can_seat_the_biggest_table() -> None:
    assert len(NICKNAMES) >= MAX_PLAYERS


def test_the_pool_has_no_twins() -> None:
    assert len({nickname.casefold() for nickname in NICKNAMES}) == len(NICKNAMES)


def test_every_nickname_fits_on_a_card() -> None:
    assert all(0 < len(nickname) <= MAX_NAME_LENGTH for nickname in NICKNAMES)


@pytest.mark.parametrize("count", [0, 1, MAX_PLAYERS])
def test_it_gives_exactly_as_many_names_as_asked(count: int) -> None:
    picked = pick_nicknames(count, (), rng())

    assert len(picked) == count
    assert set(picked) <= set(NICKNAMES)


def test_the_names_never_repeat_each_other() -> None:
    picked = pick_nicknames(MAX_PLAYERS, (), rng())

    assert len(set(picked)) == len(picked)


@pytest.mark.parametrize("taken", [("Игуана",), ("игуана",), ("ИГУАНА",)])
def test_a_taken_name_stays_out_of_the_draw(taken: tuple[str, ...]) -> None:
    picked = pick_nicknames(len(NICKNAMES) - 1, taken, rng())

    assert "Игуана" not in picked


def test_names_from_outside_the_pool_cost_nothing() -> None:
    picked = pick_nicknames(len(NICKNAMES), ("Аня", "Борис"), rng())

    assert sorted(picked) == sorted(NICKNAMES)


def test_the_draw_is_not_always_the_same_order() -> None:
    draws = {pick_nicknames(MAX_PLAYERS, (), Random(seed)) for seed in range(8)}

    assert len(draws) > 1
