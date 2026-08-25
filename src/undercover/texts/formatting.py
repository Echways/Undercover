from collections.abc import Iterable, Sequence
from datetime import timedelta

from undercover.game.models import Ruleset, Winner
from undercover.texts.strings import (
    BAR_CELLS,
    BAR_EMPTY,
    BAR_FULL,
    MINUTES_IN_HOUR,
    Buttons,
    Cards,
    Errors,
    Setup,
    Timer,
    Vote,
)
from undercover.texts.tables import RULESET_NAMES, WIN_LINES


def win_line(winner: Winner, *, misfire: bool = False) -> str:
    if winner is Winner.SPIES and misfire:
        return Vote.SPIES_WIN_MISFIRE
    return WIN_LINES[winner]


def empty_catalog_text(category_ids: Sequence[int]) -> str:
    return Errors.EMPTY_CATEGORIES if category_ids else Errors.EMPTY_CATALOG


def chosen_categories_text(titles: Iterable[str]) -> str:
    return ", ".join(titles) or Setup.ALL_CATEGORIES


def plural(count: int, forms: tuple[str, str, str]) -> str:
    if 11 <= count % 100 <= 14:
        return forms[2]
    match count % 10:
        case 1:
            return forms[0]
        case 2 | 3 | 4:
            return forms[1]
        case _:
            return forms[2]


def duration_text(spent: timedelta) -> str:
    minutes = int(spent.total_seconds()) // 60
    if minutes < 1:
        return Cards.SUMMARY_SHORT_GAME

    hours, rest = divmod(minutes, MINUTES_IN_HOUR)
    if not hours:
        return Cards.SUMMARY_MINUTES.format(minutes=minutes)
    return Cards.SUMMARY_HOURS.format(hours=hours, minutes=rest)


def countdown_line(seconds_left: int, total: int) -> str:
    filled = round(BAR_CELLS * seconds_left / total) if total > 0 else 0
    return Timer.COUNTDOWN.format(
        bar=BAR_FULL * filled + BAR_EMPTY * (BAR_CELLS - filled), seconds=seconds_left
    )


def ruleset_label(ruleset: Ruleset) -> str:
    return Buttons.RULESET.format(name=RULESET_NAMES[ruleset])


def turn_label(seconds: int) -> str:
    return Buttons.TURN_OFF if seconds <= 0 else Buttons.TURN_LIMIT.format(seconds=seconds)


def spies_label(count: int) -> str:
    return Buttons.SPIES_COUNT.format(count=count)
