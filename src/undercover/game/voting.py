from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from undercover.game.engine import GameRulesError
from undercover.game.models import (
    Ballot,
    Direction,
    GameMode,
    GameSessionState,
    PlayerState,
    Winner,
)


class Refusal(StrEnum):
    NOT_A_VOTER = "not_a_voter"
    IS_OUT = "is_out"
    ALREADY_VOTED = "already_voted"
    UNKNOWN_OPTION = "unknown_option"


@dataclass(frozen=True, slots=True)
class Verdict:
    counts: dict[str, int]
    eliminated: int | None = None
    revote: tuple[str, ...] | None = None


def alive(state: GameSessionState) -> list[PlayerState]:
    return [player for player in state.players if not player.is_out]


def electorate(state: GameSessionState) -> list[int]:
    if state.mode is not GameMode.GROUP:
        return [state.host_user_id]
    return [player.user_id for player in alive(state) if player.user_id is not None]


def open_ballot(state: GameSessionState, options: Sequence[str], *, revote: bool = False) -> None:
    state.ballot = Ballot(options=list(options), revote=revote)


def close_ballot(state: GameSessionState) -> None:
    state.ballot = None


def cast(state: GameSessionState, voter_id: int, option: str) -> Refusal | None:
    ballot = state.ballot
    if ballot is None or option not in ballot.options:
        return Refusal.UNKNOWN_OPTION
    if voter_id not in electorate(state):
        return Refusal.IS_OUT if _is_eliminated(state, voter_id) else Refusal.NOT_A_VOTER
    if voter_id in ballot.votes:
        return Refusal.ALREADY_VOTED

    ballot.votes[voter_id] = option
    return None


def tally(ballot: Ballot) -> dict[str, int]:
    counts = dict.fromkeys(ballot.options, 0)
    for option in ballot.votes.values():
        counts[option] += 1
    return counts


def turnout(state: GameSessionState) -> tuple[int, int]:
    given = 0 if state.ballot is None else len(state.ballot.votes)
    return given, len(electorate(state))


def direction_result(state: GameSessionState) -> Direction | None:
    ballot = state.ballot
    if ballot is None:
        return None

    given, total = turnout(state)
    majority = total // 2 + 1
    for option, count in tally(ballot).items():
        if count >= majority:
            return Direction(option)
    return Direction.ROUND if given >= total else None


def elimination_result(state: GameSessionState) -> Verdict | None:
    ballot = state.ballot
    if ballot is None:
        return None

    given, total = turnout(state)
    if given < total:
        return None

    counts = tally(ballot)
    best = max(counts.values())
    leaders = tuple(option for option, count in counts.items() if count == best)
    if len(leaders) == 1:
        return Verdict(counts=counts, eliminated=int(leaders[0]))
    return Verdict(counts=counts) if ballot.revote else Verdict(counts=counts, revote=leaders)


def eliminate(state: GameSessionState, order_index: int) -> PlayerState:
    player = next(
        (candidate for candidate in alive(state) if candidate.order_index == order_index),
        None,
    )
    if player is None:
        raise GameRulesError(f"игрока {order_index} нет среди живых")

    player.is_out = True
    close_ballot(state)
    return player


def outcome(state: GameSessionState) -> Winner | None:
    living = alive(state)
    spies = [player for player in living if player.is_spy]
    if not spies:
        return Winner.CIVILIANS
    return Winner.SPIES if len(spies) >= len(living) - len(spies) else None


def _is_eliminated(state: GameSessionState, voter_id: int) -> bool:
    return any(player.user_id == voter_id and player.is_out for player in state.players)
