from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field


class Role(StrEnum):
    CIVILIAN = "civilian"
    SPY = "spy"


class GameMode(StrEnum):
    HOT_SEAT = "hot_seat"
    GROUP = "group"


class PlayerState(BaseModel):
    order_index: int = Field(ge=0)

    name: str
    is_spy: bool
    has_viewed: bool = False
    is_out: bool = False
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


class Ballot(BaseModel):
    options: list[str] = Field(min_length=1)
    votes: dict[int, str] = Field(default_factory=dict)
    revote: bool = False


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
    mode: GameMode = GameMode.HOT_SEAT
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

    ballot: Ballot | None = None

    winner: Winner | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


DEFAULT_TURN_SECONDS: Final = 45

TURN_CHOICES: Final = (30, 45, 60, 0)


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

    spies_count: int = Field(default=1, ge=1)

    category_ids: list[int] = Field(default_factory=list)

    turn_seconds: int = Field(default=DEFAULT_TURN_SECONDS, ge=0)

    view: LobbyView = LobbyView.ROSTER

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def index_of(self, user_id: int) -> int | None:
        return next(
            (index for index, player in enumerate(self.players) if player.user_id == user_id),
            None,
        )
