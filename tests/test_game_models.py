from typing import Any

import pytest
from pydantic import ValidationError

from undercover.game.models import PlayerState, Role, WordWithHints


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
