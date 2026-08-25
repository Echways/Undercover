from collections.abc import Hashable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from undercover.game.settings import (
    DEFAULT_TURN_SECONDS,
    TURN_CHOICES,
    GameSettings,
    Ruleset,
)

__all__ = [
    "DEFAULT_TURN_SECONDS",
    "TURN_CHOICES",
    "AnyBallot",
    "Ballot",
    "Direction",
    "DirectionBallot",
    "EliminationBallot",
    "GameSessionState",
    "GameSettings",
    "GameStatus",
    "LobbyPlayer",
    "LobbyState",
    "LobbyView",
    "PlayerState",
    "Role",
    "Ruleset",
    "Seating",
    "Winner",
    "WordWithHints",
    "speaker_at",
]


class Role(StrEnum):
    CIVILIAN = "civilian"
    SPY = "spy"


class Seating(StrEnum):
    HOT_SEAT = "hot_seat"
    GROUP = "group"


class PlayerState(BaseModel):
    order_index: int = Field(ge=0)

    name: str
    is_spy: bool
    has_viewed: bool = False
    is_out: bool = False
    out_order: int | None = Field(default=None, gt=0)
    card_file_id: str | None = None
    user_id: int | None = None

    @property
    def role(self) -> Role:
        return Role.SPY if self.is_spy else Role.CIVILIAN


class WordWithHints(BaseModel):
    model_config = ConfigDict(frozen=True)

    word_id: int
    text: str
    hints: tuple[str, ...]


class Winner(StrEnum):
    CIVILIANS = "civilians"
    SPIES = "spies"


class Direction(StrEnum):
    ROUND = "round"
    VOTE = "vote"


class Ballot[OptionT: Hashable](BaseModel):
    options: list[OptionT] = Field(min_length=1)
    votes: dict[int, OptionT] = Field(default_factory=dict)


class DirectionBallot(Ballot[Direction]):
    kind: Literal["direction"] = "direction"


class EliminationBallot(Ballot[int]):
    kind: Literal["elimination"] = "elimination"
    revote: bool = False


AnyBallot = Annotated[DirectionBallot | EliminationBallot, Field(discriminator="kind")]


class GameStatus(StrEnum):
    SETUP = "setup"
    REVEAL = "reveal"
    DISCUSSION = "discussion"
    VOTING = "voting"
    FINISHED = "finished"


class GameSessionState(BaseModel):
    session_id: str
    chat_id: int
    host_user_id: int
    seating: Seating = Seating.HOT_SEAT
    ruleset: Ruleset = Ruleset.CLASSIC
    status: GameStatus
    players: list[PlayerState]

    word_id: int
    word_text: str
    category_ids: list[int] = Field(default_factory=list)
    hint_by_spy: dict[int, str] = Field(default_factory=dict)

    reveal_cursor: int = Field(default=0, ge=0)
    discussion_order: list[int] = Field(default_factory=list)
    discussion_cursor: int = Field(default=0, ge=0)
    discussion_round: int = Field(default=1, ge=1)
    current_message_id: int | None = None

    turn_seconds: int = Field(default=0, ge=0)
    turn_deadline: datetime | None = None

    ballot: AnyBallot | None = None
    winner: Winner | None = None
    case_number: int | None = Field(default=None, gt=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None


class LobbyView(StrEnum):
    ROSTER = "roster"
    CATEGORIES = "categories"


class LobbyPlayer(BaseModel):
    user_id: int
    name: str


class LobbyState(BaseModel):
    chat_id: int
    host_user_id: int
    message_id: int | None = None

    players: list[LobbyPlayer] = Field(default_factory=list)
    settings: GameSettings = Field(default_factory=GameSettings)

    view: LobbyView = LobbyView.ROSTER
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def index_of(self, user_id: int) -> int | None:
        return next(
            (index for index, player in enumerate(self.players) if player.user_id == user_id),
            None,
        )


def speaker_at(state: GameSessionState, cursor: int) -> PlayerState | None:
    if not 0 <= cursor < len(state.discussion_order):
        return None
    order_index = state.discussion_order[cursor]
    if not 0 <= order_index < len(state.players):
        return None
    return state.players[order_index]
