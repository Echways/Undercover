from collections.abc import Mapping
from enum import StrEnum
from typing import Final

from aiogram.filters.callback_data import CallbackData

from undercover.game.models import Direction


class RevealAction(StrEnum):
    SHOW = "show"
    NEXT = "next"


class RevealCB(CallbackData, prefix="reveal"):
    action: RevealAction
    session_id: str
    order_index: int


class TalkAction(StrEnum):
    NEXT = "next"
    ROUND = "round"
    VOTE = "vote"
    SPIES = "spies"


class TalkCB(CallbackData, prefix="talk"):
    action: TalkAction
    session_id: str
    cursor: int


DIRECTIONS: Final[Mapping[TalkAction, Direction]] = {
    TalkAction.ROUND: Direction.ROUND,
    TalkAction.VOTE: Direction.VOTE,
}


class VoteAction(StrEnum):
    BACK = "back"
    CONTINUE = "continue"


class VoteCB(CallbackData, prefix="vote"):
    action: VoteAction
    session_id: str


class PickCB(CallbackData, prefix="pick"):
    session_id: str
    order_index: int


class FinalAction(StrEnum):
    AGAIN = "again"
    NEW = "new"
    RESULT = "result"


class FinalCB(CallbackData, prefix="final"):
    action: FinalAction
    session_id: str


class LobbyAction(StrEnum):
    JOIN = "join"
    LEAVE = "leave"
    SPIES = "spies"
    TURN = "turn"
    CATEGORIES = "cats"
    CATEGORY = "cat"
    DONE = "done"
    RULESET = "ruleset"
    RULES = "rules"
    PLAY = "play"


class LobbyCB(CallbackData, prefix="lobby"):
    action: LobbyAction
    value: int = 0


class StatsAction(StrEnum):
    BOARD = "board"
    ME = "me"


class StatsCB(CallbackData, prefix="stats"):
    action: StatsAction
