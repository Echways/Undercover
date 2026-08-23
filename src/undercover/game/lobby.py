from collections.abc import Iterable

from undercover.game.engine import (
    MAX_NAME_LENGTH,
    MAX_PLAYERS,
    MIN_PLAYERS,
    GameRulesError,
    max_spies_count,
)
from undercover.game.models import TURN_CHOICES, LobbyPlayer, LobbyState, Ruleset


def join(lobby: LobbyState, player: LobbyPlayer) -> None:
    if lobby.index_of(player.user_id) is not None:
        raise GameRulesError(f"{player.name} уже в составе")
    if len(lobby.players) >= MAX_PLAYERS:
        raise GameRulesError(f"в составе уже {MAX_PLAYERS} игроков — больше не поместится")
    lobby.players.append(player)


def seat(lobby: LobbyState, user_id: int, full_name: str) -> None:
    taken = [member.name for member in lobby.players]
    join(lobby, LobbyPlayer(user_id=user_id, name=unique_name(full_name, taken)))


def leave(lobby: LobbyState, user_id: int) -> None:
    index = lobby.index_of(user_id)
    if index is None:
        raise GameRulesError("этого игрока нет в составе")
    del lobby.players[index]
    _clamp_spies(lobby)


def cycle_spies_count(lobby: LobbyState) -> None:
    lobby.spies_count = lobby.spies_count % _spies_limit(lobby) + 1


def cycle_turn_seconds(lobby: LobbyState) -> None:
    position = (
        TURN_CHOICES.index(lobby.turn_seconds) + 1 if lobby.turn_seconds in TURN_CHOICES else 0
    )
    lobby.turn_seconds = TURN_CHOICES[position % len(TURN_CHOICES)]


def toggle_ruleset(lobby: LobbyState) -> None:
    lobby.ruleset = Ruleset.SUDDEN_DEATH if lobby.ruleset is Ruleset.CLASSIC else Ruleset.CLASSIC


def toggle_category(lobby: LobbyState, category_id: int) -> None:
    if category_id in lobby.category_ids:
        lobby.category_ids.remove(category_id)
    else:
        lobby.category_ids.append(category_id)


def ensure_playable(lobby: LobbyState) -> None:
    if len(lobby.players) < MIN_PLAYERS:
        raise GameRulesError(f"для партии нужно хотя бы {MIN_PLAYERS} игрока")
    _clamp_spies(lobby)


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

    raise GameRulesError(f"не удалось развести имя «{base}»")


def _spies_limit(lobby: LobbyState) -> int:
    return max_spies_count(len(lobby.players)) if lobby.players else 1


def _clamp_spies(lobby: LobbyState) -> None:
    lobby.spies_count = min(lobby.spies_count, _spies_limit(lobby))
