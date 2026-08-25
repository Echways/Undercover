from collections.abc import Iterable

from undercover.game.engine import MAX_NAME_LENGTH, MAX_PLAYERS, MIN_PLAYERS
from undercover.game.models import LobbyPlayer, LobbyState
from undercover.game.rules import GameRulesError, Rule
from undercover.game.settings import clamp_spies


def join(lobby: LobbyState, player: LobbyPlayer) -> None:
    if lobby.index_of(player.user_id) is not None:
        raise GameRulesError(Rule.ALREADY_SEATED)
    if len(lobby.players) >= MAX_PLAYERS:
        raise GameRulesError(Rule.LOBBY_FULL)
    lobby.players.append(player)


def seat(lobby: LobbyState, user_id: int, full_name: str) -> None:
    taken = [member.name for member in lobby.players]
    join(lobby, LobbyPlayer(user_id=user_id, name=unique_name(full_name, taken)))


def leave(lobby: LobbyState, user_id: int) -> None:
    index = lobby.index_of(user_id)
    if index is None:
        raise GameRulesError(Rule.NOT_SEATED)
    del lobby.players[index]
    clamp_spies(lobby.settings, len(lobby.players))


def ensure_playable(lobby: LobbyState) -> None:
    if len(lobby.players) < MIN_PLAYERS:
        raise GameRulesError(Rule.TOO_FEW_PLAYERS)
    if lobby.index_of(lobby.host_user_id) is None:
        raise GameRulesError(Rule.HOST_MUST_PLAY)
    clamp_spies(lobby.settings, len(lobby.players))


def unique_name(base: str, taken: Iterable[str]) -> str:
    reserved = set(taken)
    trimmed = base[:MAX_NAME_LENGTH]
    if trimmed not in reserved:
        return trimmed

    for number in range(2, MAX_PLAYERS + 2):
        suffix = f" {number}"
        candidate = f"{base[: MAX_NAME_LENGTH - len(suffix)]}{suffix}"
        if candidate not in reserved:
            return candidate

    raise GameRulesError(Rule.NAME_CLASH)
