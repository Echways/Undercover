from typing import Any

import pytest
from pydantic import ValidationError

from undercover.game.models import (
    GameMode,
    GameSessionState,
    LobbyPlayer,
    LobbyState,
    PlayerState,
    Role,
    WordWithHints,
)


def test_player_starts_with_no_viewed_card() -> None:
    player = PlayerState(order_index=0, name="Аня", is_spy=False)

    assert player.has_viewed is False
    assert player.card_file_id is None


def test_role_follows_the_is_spy_flag() -> None:
    assert PlayerState(order_index=0, name="Аня", is_spy=True).role is Role.SPY
    assert PlayerState(order_index=1, name="Боря", is_spy=False).role is Role.CIVILIAN


def test_players_with_equal_fields_are_equal() -> None:
    assert PlayerState(order_index=0, name="Аня", is_spy=True) == PlayerState(
        order_index=0, name="Аня", is_spy=True
    )


def test_word_with_hints_is_immutable() -> None:
    word: Any = WordWithHints(word_id=1, text="пицца", hints=["её режут на куски"])

    with pytest.raises(ValidationError):
        word.text = "паста"


def test_lobby_finds_a_player_by_telegram_id_and_misses_a_stranger() -> None:
    lobby = LobbyState(
        chat_id=-100,
        host_user_id=1,
        players=[LobbyPlayer(user_id=1, name="Аня"), LobbyPlayer(user_id=2, name="Борис")],
    )

    assert lobby.index_of(2) == 1
    assert lobby.index_of(99) is None


def test_old_sessions_without_the_new_fields_still_read_as_hot_seat() -> None:
    raw = (
        '{"session_id": "s", "chat_id": -100, "host_user_id": 1, "status": "discussion",'
        ' "players": [{"order_index": 0, "name": "Аня", "is_spy": false}],'
        ' "word_id": 1, "word_text": "пицца"}'
    )

    state = GameSessionState.model_validate_json(raw)

    assert state.mode is GameMode.HOT_SEAT
    assert state.players[0].user_id is None
