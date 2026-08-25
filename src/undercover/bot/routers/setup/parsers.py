from undercover.game.engine import MAX_NAME_LENGTH, MAX_PLAYERS, MIN_PLAYERS
from undercover.texts import Setup as SetupTexts


def parse_count(text: str) -> int:
    try:
        return int(text.strip())
    except ValueError:
        raise ValueError(SetupTexts.NOT_A_NUMBER) from None


def parse_players_count(text: str) -> int:
    count = parse_count(text)
    if not MIN_PLAYERS <= count <= MAX_PLAYERS:
        raise ValueError(SetupTexts.BAD_PLAYERS_COUNT)
    return count


def parse_name(text: str) -> str:
    name = " ".join(text.split())
    if not name:
        raise ValueError(SetupTexts.EMPTY_NAME)
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(SetupTexts.TOO_LONG_NAME)
    return name
