from collections.abc import Mapping
from typing import Final

from undercover.game.models import Ruleset, Winner
from undercover.game.rules import Rule
from undercover.game.voting import Refusal
from undercover.texts.strings import Cards, Errors, Lobby, Vote

VOTE_REFUSALS: Final[Mapping[Refusal, str]] = {
    Refusal.NOT_A_VOTER: Vote.NOT_A_VOTER,
    Refusal.IS_OUT: Vote.IS_OUT,
    Refusal.ALREADY_VOTED: Vote.ALREADY_VOTED,
    Refusal.UNKNOWN_OPTION: Vote.STALE_OPTION,
}

RULE_REFUSALS: Final[Mapping[Rule, str]] = {
    Rule.ALREADY_SEATED: Lobby.ALREADY_IN,
    Rule.LOBBY_FULL: Lobby.FULL,
    Rule.NOT_SEATED: Lobby.NOT_IN,
    Rule.TOO_FEW_PLAYERS: Lobby.TOO_FEW,
    Rule.HOST_MUST_PLAY: Lobby.HOST_MUST_PLAY,
    Rule.NAME_CLASH: Lobby.NAME_CLASH,
    Rule.ROSTER_SIZE: Errors.BROKEN_SESSION,
    Rule.IDS_MISMATCH: Errors.BROKEN_SESSION,
    Rule.SPIES_COUNT: Errors.BROKEN_SESSION,
    Rule.NO_SPEAKERS: Errors.BROKEN_SESSION,
    Rule.NO_SPIES: Errors.BROKEN_SESSION,
    Rule.NOT_ALIVE: Errors.BROKEN_SESSION,
    Rule.BROKEN_ORDER: Errors.BROKEN_SESSION,
}

WIN_CAPTIONS: Final[Mapping[Winner, str]] = {
    Winner.CIVILIANS: Cards.WIN_CIVILIANS,
    Winner.SPIES: Cards.WIN_SPIES,
}

WIN_LINES: Final[Mapping[Winner, str]] = {
    Winner.CIVILIANS: Vote.CIVILIANS_WIN,
    Winner.SPIES: Vote.SPIES_WIN,
}

RULESET_NAMES: Final[Mapping[Ruleset, str]] = {
    Ruleset.CLASSIC: "классика",
    Ruleset.SUDDEN_DEATH: "навылет",
}

RULESET_LINES: Final[Mapping[Ruleset, str]] = {
    Ruleset.CLASSIC: Lobby.RULESET_CLASSIC,
    Ruleset.SUDDEN_DEATH: Lobby.RULESET_SUDDEN_DEATH,
}
