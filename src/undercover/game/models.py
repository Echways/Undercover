from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Role(StrEnum):
    CIVILIAN = "civilian"
    SPY = "spy"


class PlayerState(BaseModel):
    order_index: int = Field(ge=0)

    name: str
    is_spy: bool
    has_viewed: bool = False
    card_file_id: str | None = None

    @property
    def role(self) -> Role:
        return Role.SPY if self.is_spy else Role.CIVILIAN


class WordWithHints(BaseModel):
    model_config = ConfigDict(frozen=True)

    word_id: int
    text: str
    hints: tuple[str, ...]


class GameStatus(StrEnum):
    SETUP = "setup"
    REVEAL = "reveal"
    DISCUSSION = "discussion"
    FINISHED = "finished"


class GameSessionState(BaseModel):
    session_id: str
    chat_id: int
    host_user_id: int
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

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
