from typing import Any

import pytest
from pydantic import ValidationError

from undercover.game.models import (
    Direction,
    DirectionBallot,
    EliminationBallot,
    GameMode,
    GameSessionState,
    GameStatus,
    LobbyPlayer,
    LobbyState,
    PlayerState,
    Role,
    Winner,
    WordWithHints,
)


def make_session(**overrides: Any) -> GameSessionState:
    defaults: dict[str, Any] = {
        "session_id": "11111111-1111-1111-1111-111111111111",
        "chat_id": -100,
        "host_user_id": 777,
        "status": GameStatus.DISCUSSION,
        "players": [
            PlayerState(order_index=0, name="Аня", is_spy=True),
            PlayerState(order_index=1, name="Борис", is_spy=False),
        ],
        "word_id": 1,
        "word_text": "пицца",
    }
    return GameSessionState.model_validate(defaults | overrides)


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


def test_a_player_starts_the_game_alive() -> None:
    player = PlayerState(order_index=0, name="Аня", is_spy=False)

    assert not player.is_out


def test_a_fresh_ballot_holds_no_votes() -> None:
    ballot = DirectionBallot(options=[Direction.ROUND, Direction.VOTE])

    assert ballot.votes == {}


def test_a_fresh_elimination_ballot_is_not_a_revote() -> None:
    assert not EliminationBallot(options=[0, 1]).revote


def test_a_ballot_without_options_is_refused() -> None:
    with pytest.raises(ValidationError):
        EliminationBallot(options=[])


def test_a_ballot_keeps_a_vote_per_voter() -> None:
    ballot = EliminationBallot(options=[0, 1], votes={111: 0, 222: 1})

    assert ballot.votes == {111: 0, 222: 1}


def test_an_elimination_ballot_holds_order_indices() -> None:
    assert EliminationBallot(options=[0, 1]).options == [0, 1]


def test_a_direction_ballot_holds_directions() -> None:
    ballot = DirectionBallot(options=[Direction.ROUND, Direction.VOTE])

    assert ballot.options == [Direction.ROUND, Direction.VOTE]


def test_a_game_starts_without_a_ballot_and_without_a_winner() -> None:
    state = make_session()

    assert state.ballot is None
    assert state.winner is None


def test_a_finished_game_remembers_who_won() -> None:
    state = make_session(status=GameStatus.FINISHED, winner=Winner.SPIES)

    assert state.winner is Winner.SPIES


def test_a_saved_game_survives_a_round_trip_through_json() -> None:
    state = make_session(
        status=GameStatus.VOTING,
        ballot=EliminationBallot(options=[0, 1], votes={111: 0}, revote=True),
    )

    restored = GameSessionState.model_validate_json(state.model_dump_json())

    assert restored.ballot == state.ballot
    assert restored.status is GameStatus.VOTING


def test_a_direction_ballot_survives_a_round_trip_through_json() -> None:
    state = make_session(
        status=GameStatus.DISCUSSION,
        ballot=DirectionBallot(options=[Direction.ROUND], votes={111: Direction.ROUND}),
    )

    restored = GameSessionState.model_validate_json(state.model_dump_json())

    assert isinstance(restored.ballot, DirectionBallot)
    assert restored.ballot == state.ballot


def test_games_saved_before_voting_existed_still_read() -> None:
    older = {
        "session_id": "11111111-1111-1111-1111-111111111111",
        "chat_id": -100,
        "host_user_id": 777,
        "status": "discussion",
        "players": [{"order_index": 0, "name": "Аня", "is_spy": True}],
        "word_id": 1,
        "word_text": "пицца",
    }

    state = GameSessionState.model_validate(older)

    assert state.ballot is None
    assert state.winner is None
    assert not state.players[0].is_out


def test_a_fresh_player_is_not_in_the_elimination_queue() -> None:
    player = PlayerState(order_index=0, name="Аня", is_spy=False)

    assert player.out_order is None


def test_the_elimination_place_starts_from_one() -> None:
    with pytest.raises(ValidationError):
        PlayerState(order_index=0, name="Аня", is_spy=False, out_order=0)
