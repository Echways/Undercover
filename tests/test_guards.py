from typing import Final

import pytest

from fake_bot import CHAT_ID, HOST_ID
from undercover.bot.guards import may_act
from undercover.game.models import (
    EliminationBallot,
    GameSessionState,
    GameStatus,
    PlayerState,
    Seating,
)

SESSION_ID: Final = "11111111-1111-1111-1111-111111111111"
OPEN_BALLOT: Final = EliminationBallot(options=[0, 1])
SPEAKER_ID: Final = 111
BYSTANDER_ID: Final = 222


def make_state(
    seating: Seating = Seating.GROUP,
    status: GameStatus = GameStatus.DISCUSSION,
    **overrides: object,
) -> GameSessionState:
    defaults: dict[str, object] = {
        "session_id": SESSION_ID,
        "chat_id": CHAT_ID,
        "host_user_id": HOST_ID,
        "seating": seating,
        "status": status,
        "players": [
            PlayerState(order_index=0, name="Аня", is_spy=True, user_id=SPEAKER_ID),
            PlayerState(order_index=1, name="Борис", is_spy=False, user_id=BYSTANDER_ID),
        ],
        "word_id": 1,
        "word_text": "пицца",
        "discussion_order": [0, 1],
        "discussion_cursor": 0,
    }
    return GameSessionState.model_validate(defaults | overrides)


def test_the_host_may_always_act() -> None:
    assert may_act(make_state(), HOST_ID)
    assert may_act(make_state(Seating.HOT_SEAT), HOST_ID)
    assert may_act(make_state(status=GameStatus.FINISHED), HOST_ID)


def test_the_current_speaker_may_end_their_own_turn() -> None:
    assert may_act(make_state(), SPEAKER_ID)


def test_a_player_waiting_for_their_turn_may_not() -> None:
    assert not may_act(make_state(), BYSTANDER_ID)


def test_the_previous_speaker_loses_the_right_when_the_turn_moves_on() -> None:
    assert not may_act(make_state(discussion_cursor=1), SPEAKER_ID)
    assert may_act(make_state(discussion_cursor=1), BYSTANDER_ID)


def test_hot_seat_leaves_every_button_to_the_host() -> None:
    assert not may_act(make_state(Seating.HOT_SEAT), SPEAKER_ID)


@pytest.mark.parametrize("status", [GameStatus.REVEAL, GameStatus.FINISHED, GameStatus.SETUP])
def test_outside_the_discussion_there_is_no_speaker(status: GameStatus) -> None:
    assert not may_act(make_state(status=status), SPEAKER_ID)


def test_a_broken_order_does_not_hand_the_buttons_to_anyone() -> None:
    assert not may_act(make_state(discussion_order=[9], discussion_cursor=0), SPEAKER_ID)
    assert not may_act(make_state(discussion_order=[], discussion_cursor=0), SPEAKER_ID)
    assert not may_act(make_state(discussion_cursor=5), SPEAKER_ID)


def test_a_hot_seat_player_without_a_telegram_id_is_never_mistaken_for_a_speaker() -> None:
    state = make_state()
    for player in state.players:
        player.user_id = None

    assert not may_act(state, SPEAKER_ID)


def test_an_open_ballot_hands_a_button_to_every_player() -> None:
    state = make_state(status=GameStatus.VOTING, ballot=OPEN_BALLOT)

    assert may_act(state, SPEAKER_ID)
    assert may_act(state, BYSTANDER_ID)


def test_an_eliminated_player_still_reaches_the_ballot_to_be_told_they_are_out() -> None:
    state = make_state(status=GameStatus.VOTING, ballot=OPEN_BALLOT)
    state.players[1].is_out = True

    assert may_act(state, BYSTANDER_ID)


def test_someone_who_never_played_gets_nothing() -> None:
    state = make_state(status=GameStatus.VOTING, ballot=OPEN_BALLOT)

    assert not may_act(state, 999)


def test_a_closed_ballot_gives_the_voting_screen_back_to_the_host() -> None:
    state = make_state(status=GameStatus.VOTING)

    assert not may_act(state, BYSTANDER_ID)
    assert may_act(state, HOST_ID)


def test_hot_seat_voting_stays_with_the_host() -> None:
    state = make_state(Seating.HOT_SEAT, status=GameStatus.VOTING, ballot=OPEN_BALLOT)

    assert not may_act(state, SPEAKER_ID)
    assert may_act(state, HOST_ID)


def test_the_direction_ballot_lets_a_player_answer_from_someone_elses_turn() -> None:
    state = make_state(ballot=OPEN_BALLOT, discussion_cursor=0)

    assert may_act(state, BYSTANDER_ID)
