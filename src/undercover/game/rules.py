from enum import StrEnum


class Rule(StrEnum):
    ALREADY_SEATED = "already_seated"
    LOBBY_FULL = "lobby_full"
    NOT_SEATED = "not_seated"
    TOO_FEW_PLAYERS = "too_few_players"
    HOST_MUST_PLAY = "host_must_play"
    NAME_CLASH = "name_clash"
    ROSTER_SIZE = "roster_size"
    IDS_MISMATCH = "ids_mismatch"
    SPIES_COUNT = "spies_count"
    NO_SPEAKERS = "no_speakers"
    NO_SPIES = "no_spies"
    NOT_ALIVE = "not_alive"
    BROKEN_ORDER = "broken_order"


class GameRulesError(ValueError):
    def __init__(self, rule: Rule) -> None:
        super().__init__(rule.value)
        self.rule = rule
