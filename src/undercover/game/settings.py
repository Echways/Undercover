from enum import StrEnum
from typing import Final

from pydantic import BaseModel, Field

DEFAULT_TURN_SECONDS: Final = 45

TURN_CHOICES: Final = (30, 45, 60, 0)

SPIES_PER_PLAYERS: Final = 3


class Ruleset(StrEnum):
    CLASSIC = "classic"
    SUDDEN_DEATH = "sudden_death"


class GameSettings(BaseModel):
    spies_count: int = Field(default=1, ge=1)
    turn_seconds: int = Field(default=DEFAULT_TURN_SECONDS, ge=0)
    ruleset: Ruleset = Ruleset.CLASSIC
    category_ids: list[int] = Field(default_factory=list)


def max_spies_count(players_count: int) -> int:
    return max(1, players_count // SPIES_PER_PLAYERS)


def cycle_spies(settings: GameSettings, players_count: int) -> None:
    limit = max_spies_count(players_count) if players_count else 1
    settings.spies_count = settings.spies_count % limit + 1


def cycle_turn_seconds(settings: GameSettings) -> None:
    position = (
        TURN_CHOICES.index(settings.turn_seconds) + 1
        if settings.turn_seconds in TURN_CHOICES
        else 0
    )
    settings.turn_seconds = TURN_CHOICES[position % len(TURN_CHOICES)]


def toggle_ruleset(settings: GameSettings) -> None:
    settings.ruleset = (
        Ruleset.SUDDEN_DEATH if settings.ruleset is Ruleset.CLASSIC else Ruleset.CLASSIC
    )


def toggle_category(settings: GameSettings, category_id: int) -> None:
    if category_id in settings.category_ids:
        settings.category_ids.remove(category_id)
    else:
        settings.category_ids.append(category_id)


def clamp_spies(settings: GameSettings, players_count: int) -> None:
    limit = max_spies_count(players_count) if players_count else 1
    settings.spies_count = min(settings.spies_count, limit)
