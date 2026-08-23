from typing import Any, Final

import pytest

from undercover.game.engine import GameRulesError
from undercover.game.models import (
    Direction,
    EliminationBallot,
    GameMode,
    GameSessionState,
    GameStatus,
    PlayerState,
    Winner,
)
from undercover.game.voting import (
    Refusal,
    Verdict,
    alive,
    cast_direction,
    cast_elimination,
    close_ballot,
    direction_result,
    electorate,
    eliminate,
    elimination_result,
    open_direction_ballot,
    open_elimination_ballot,
    outcome,
    tally,
    turnout,
)

CHAT_ID: Final = -1001234567890
HOST_ID: Final = 777
NAMES: Final = ("Аня", "Борис", "Вера", "Галя", "Дима")


def make_state(
    spies: tuple[int, ...] = (1,),
    out: tuple[int, ...] = (),
    players: int = 4,
    mode: GameMode = GameMode.GROUP,
    **overrides: Any,
) -> GameSessionState:
    defaults: dict[str, Any] = {
        "session_id": "11111111-1111-1111-1111-111111111111",
        "chat_id": CHAT_ID,
        "host_user_id": HOST_ID,
        "mode": mode,
        "status": GameStatus.VOTING,
        "players": [
            PlayerState(
                order_index=index,
                name=NAMES[index],
                is_spy=index in spies,
                is_out=index in out,
                user_id=None if mode is GameMode.HOT_SEAT else 100 + index,
            )
            for index in range(players)
        ],
        "word_id": 1,
        "word_text": "пицца",
    }
    return GameSessionState.model_validate(defaults | overrides)


def test_everyone_is_alive_until_someone_is_voted_out() -> None:
    assert [player.name for player in alive(make_state())] == list(NAMES[:4])


def test_the_eliminated_leave_the_living() -> None:
    assert [player.name for player in alive(make_state(out=(1,)))] == ["Аня", "Вера", "Галя"]


def test_the_group_electorate_is_every_living_player() -> None:
    assert electorate(make_state(out=(0,))) == [101, 102, 103]


def test_the_hot_seat_electorate_is_the_host_alone() -> None:
    assert electorate(make_state(mode=GameMode.HOT_SEAT)) == [HOST_ID]


def test_a_group_player_without_a_telegram_id_cannot_vote() -> None:
    state = make_state()
    state.players[2].user_id = None

    assert electorate(state) == [100, 101, 103]


def test_opening_a_ballot_replaces_whatever_was_there() -> None:
    state = make_state(ballot=EliminationBallot(options=[3], votes={100: 3}))

    open_elimination_ballot(state, [0, 1])

    assert state.ballot == EliminationBallot(options=[0, 1])


def test_a_revote_is_marked_as_one() -> None:
    state = make_state()

    open_elimination_ballot(state, [0, 1], revote=True)

    assert isinstance(state.ballot, EliminationBallot)
    assert state.ballot.revote


def test_closing_a_ballot_leaves_nothing_behind() -> None:
    state = make_state()
    open_elimination_ballot(state, [0, 1])

    close_ballot(state)

    assert state.ballot is None


def test_an_accepted_vote_is_recorded() -> None:
    state = make_state()
    open_elimination_ballot(state, [0, 1])

    assert cast_elimination(state, 100, 1) is None
    assert state.ballot is not None
    assert state.ballot.votes == {100: 1}


def test_a_stranger_is_told_they_are_not_playing() -> None:
    state = make_state()
    open_elimination_ballot(state, [0, 1])

    assert cast_elimination(state, 999, 1) is Refusal.NOT_A_VOTER


def test_an_eliminated_player_is_told_they_are_out() -> None:
    state = make_state(out=(2,))
    open_elimination_ballot(state, [0, 1])

    assert cast_elimination(state, 102, 1) is Refusal.IS_OUT


def test_nobody_votes_twice() -> None:
    state = make_state()
    open_elimination_ballot(state, [0, 1])
    cast_elimination(state, 100, 0)

    assert cast_elimination(state, 100, 1) is Refusal.ALREADY_VOTED
    assert state.ballot is not None
    assert state.ballot.votes == {100: 0}


def test_a_button_from_a_stale_screen_is_rejected() -> None:
    state = make_state()
    open_elimination_ballot(state, [0, 1])

    assert cast_elimination(state, 100, 3) is Refusal.UNKNOWN_OPTION


def test_voting_without_a_ballot_is_rejected_too() -> None:
    assert cast_elimination(make_state(), 100, 0) is Refusal.UNKNOWN_OPTION


def test_the_tally_counts_every_option_including_the_unloved() -> None:
    state = make_state()
    open_elimination_ballot(state, [0, 1, 2])
    cast_elimination(state, 100, 0)
    cast_elimination(state, 101, 0)
    cast_elimination(state, 102, 1)

    assert isinstance(state.ballot, EliminationBallot)
    assert tally(state.ballot) == {0: 2, 1: 1, 2: 0}


def test_turnout_reports_the_votes_given_against_the_electorate() -> None:
    state = make_state()
    open_elimination_ballot(state, [0, 1])
    cast_elimination(state, 100, 0)

    assert turnout(state) == (1, 4)


def test_turnout_without_a_ballot_is_empty_but_honest_about_the_electorate() -> None:
    assert turnout(make_state()) == (0, 4)


def test_the_hot_seat_host_alone_makes_a_full_turnout() -> None:
    state = make_state(mode=GameMode.HOT_SEAT)
    open_direction_ballot(state)
    cast_direction(state, HOST_ID, Direction.VOTE)

    assert turnout(state) == (1, 1)


def steer(state: GameSessionState, choices: dict[int, Direction]) -> None:
    for voter_id, choice in choices.items():
        assert cast_direction(state, voter_id, choice) is None


def elect(state: GameSessionState, choices: dict[int, int]) -> None:
    for voter_id, order_index in choices.items():
        assert cast_elimination(state, voter_id, order_index) is None


def test_the_direction_is_undecided_while_the_table_is_still_tapping() -> None:
    state = make_state()
    open_direction_ballot(state)
    cast_direction(state, 100, Direction.VOTE)

    assert direction_result(state) is None


def test_the_direction_is_settled_by_half_the_table_plus_one() -> None:
    state = make_state()
    open_direction_ballot(state)
    steer(state, {100: Direction.VOTE, 101: Direction.VOTE, 102: Direction.VOTE})

    assert direction_result(state) is Direction.VOTE


def test_an_evenly_split_table_keeps_talking() -> None:
    state = make_state()
    open_direction_ballot(state)
    steer(
        state,
        {
            100: Direction.VOTE,
            101: Direction.VOTE,
            102: Direction.ROUND,
            103: Direction.ROUND,
        },
    )

    assert direction_result(state) is Direction.ROUND


def test_the_hot_seat_host_decides_the_direction_with_one_tap() -> None:
    state = make_state(mode=GameMode.HOT_SEAT)
    open_direction_ballot(state)
    cast_direction(state, HOST_ID, Direction.VOTE)

    assert direction_result(state) is Direction.VOTE


def test_there_is_no_direction_without_a_ballot() -> None:
    assert direction_result(make_state()) is None


def test_the_elimination_stays_silent_until_everyone_has_voted() -> None:
    state = make_state()
    open_elimination_ballot(state, [0, 1, 2, 3])
    elect(state, {100: 1, 101: 1, 102: 1})

    assert elimination_result(state) is None


def test_a_clear_majority_sends_one_player_out() -> None:
    state = make_state()
    open_elimination_ballot(state, [0, 1, 2, 3])
    elect(state, {100: 1, 101: 1, 102: 1, 103: 0})

    verdict = elimination_result(state)

    assert verdict == Verdict(counts={0: 1, 1: 3, 2: 0, 3: 0}, eliminated=1)


def test_a_tie_sends_only_the_leaders_to_a_second_round() -> None:
    state = make_state()
    open_elimination_ballot(state, [0, 1, 2, 3])
    elect(state, {100: 1, 101: 1, 102: 0, 103: 0})

    verdict = elimination_result(state)

    assert verdict is not None
    assert verdict.eliminated is None
    assert verdict.revote == (0, 1)


def test_a_second_tie_sends_nobody_out() -> None:
    state = make_state()
    open_elimination_ballot(state, [0, 1], revote=True)
    elect(state, {100: 1, 101: 1, 102: 0, 103: 0})

    verdict = elimination_result(state)

    assert verdict is not None
    assert verdict.eliminated is None
    assert verdict.revote is None


def test_the_hot_seat_host_eliminates_with_one_tap_and_never_ties() -> None:
    state = make_state(mode=GameMode.HOT_SEAT)
    open_elimination_ballot(state, [0, 1, 2, 3])
    cast_elimination(state, HOST_ID, 2)

    verdict = elimination_result(state)

    assert verdict is not None
    assert verdict.eliminated == 2


def test_there_is_no_verdict_without_a_ballot() -> None:
    assert elimination_result(make_state()) is None


def test_the_eliminated_player_leaves_and_takes_the_ballot_with_them() -> None:
    state = make_state()
    open_elimination_ballot(state, [0, 1])

    gone = eliminate(state, 1)

    assert gone.name == "Борис"
    assert gone.is_out
    assert state.ballot is None


def test_the_same_player_cannot_be_eliminated_twice() -> None:
    state = make_state(out=(1,))

    with pytest.raises(GameRulesError):
        eliminate(state, 1)


def test_an_unknown_player_cannot_be_eliminated() -> None:
    with pytest.raises(GameRulesError):
        eliminate(make_state(), 9)


def test_the_game_goes_on_while_spies_are_outnumbered() -> None:
    assert outcome(make_state(spies=(1,))) is None


def test_the_civilians_win_when_the_last_spy_is_gone() -> None:
    assert outcome(make_state(spies=(1,), out=(1,))) is Winner.CIVILIANS


def test_the_spies_win_when_they_draw_level() -> None:
    assert outcome(make_state(spies=(1,), out=(0, 2))) is Winner.SPIES


def test_two_spies_against_two_civilians_is_already_a_spy_win() -> None:
    assert outcome(make_state(spies=(0, 1), players=5)) is None
    assert outcome(make_state(spies=(0, 1), players=5, out=(4,))) is Winner.SPIES


def test_the_civilians_win_takes_priority_over_the_count() -> None:
    assert outcome(make_state(spies=(0,), out=(0, 1, 2))) is Winner.CIVILIANS


def test_the_order_of_elimination_is_remembered() -> None:
    state = make_state(players=5)

    first = eliminate(state, 3)
    second = eliminate(state, 0)

    assert (first.out_order, second.out_order) == (1, 2)


def test_a_player_who_survives_has_no_place_in_the_queue() -> None:
    state = make_state(players=5)

    eliminate(state, 3)

    assert [player.out_order for player in alive(state)] == [None, None, None, None]
