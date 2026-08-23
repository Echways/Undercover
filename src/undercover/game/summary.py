from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from undercover.game.models import GameSessionState, PlayerState, Ruleset, Winner


@dataclass(frozen=True, slots=True)
class Suspect:
    name: str
    is_spy: bool
    out_order: int | None


@dataclass(frozen=True, slots=True)
class GameSummary:
    case_number: int | None
    opened_at: datetime
    winner: Winner | None
    ruleset: Ruleset
    suspects: tuple[Suspect, ...]
    word: str
    hints: tuple[str, ...]
    rounds: int
    duration: timedelta

    @property
    def players_count(self) -> int:
        return len(self.suspects)


def summarize(state: GameSessionState) -> GameSummary:
    finished_at = state.finished_at or datetime.now(UTC)
    return GameSummary(
        case_number=state.case_number,
        opened_at=state.created_at,
        winner=state.winner,
        ruleset=state.ruleset,
        suspects=tuple(_suspect(player) for player in _ordered(state)),
        word=state.word_text,
        hints=_hints(state),
        rounds=state.discussion_round,
        duration=max(finished_at - state.created_at, timedelta()),
    )


def _ordered(state: GameSessionState) -> list[PlayerState]:
    return sorted(state.players, key=lambda player: player.order_index)


def _suspect(player: PlayerState) -> Suspect:
    return Suspect(name=player.name, is_spy=player.is_spy, out_order=player.out_order)


def _hints(state: GameSessionState) -> tuple[str, ...]:
    given = (
        state.hint_by_spy[player.order_index]
        for player in _ordered(state)
        if player.is_spy and player.order_index in state.hint_by_spy
    )
    return tuple(dict.fromkeys(given))
