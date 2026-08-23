from datetime import UTC, datetime, timedelta

from undercover.game.models import GameSessionState, GameStatus, PlayerState, Ruleset, Winner
from undercover.game.summary import summarize

STARTED_AT = datetime(2026, 8, 23, 20, 0, tzinfo=UTC)
NAMES = ("Аня", "Борис", "Вера", "Галя")
SPIES = (1, 3)


def make_state(**overrides: object) -> GameSessionState:
    defaults: dict[str, object] = {
        "session_id": "11111111-1111-1111-1111-111111111111",
        "chat_id": -100500,
        "host_user_id": 777,
        "status": GameStatus.FINISHED,
        "players": [
            PlayerState(order_index=index, name=name, is_spy=index in SPIES)
            for index, name in enumerate(NAMES)
        ],
        "word_id": 42,
        "word_text": "пицца",
        "hint_by_spy": {1: "её режут на куски", 3: "её делят на всех"},
        "created_at": STARTED_AT,
        "finished_at": STARTED_AT + timedelta(minutes=6),
        "winner": Winner.CIVILIANS,
        "discussion_round": 3,
    }
    return GameSessionState.model_validate(defaults | overrides)


def test_the_roster_keeps_the_order_players_spoke_in() -> None:
    summary = summarize(make_state())

    assert tuple(suspect.name for suspect in summary.suspects) == NAMES


def test_the_roster_remembers_who_was_a_spy() -> None:
    summary = summarize(make_state())

    assert tuple(suspect.is_spy for suspect in summary.suspects) == (False, True, False, True)


def test_the_order_of_elimination_travels_to_the_summary() -> None:
    players = [
        PlayerState(
            order_index=index,
            name=name,
            is_spy=index in SPIES,
            is_out=index == 2,
            out_order=1 if index == 2 else None,
        )
        for index, name in enumerate(NAMES)
    ]

    summary = summarize(make_state(players=players))

    assert tuple(suspect.out_order for suspect in summary.suspects) == (None, None, 1, None)


def test_one_hint_shared_by_two_spies_is_printed_once() -> None:
    summary = summarize(make_state(hint_by_spy={1: "её режут на куски", 3: "её режут на куски"}))

    assert summary.hints == ("её режут на куски",)


def test_different_hints_follow_the_order_of_the_spies() -> None:
    summary = summarize(make_state())

    assert summary.hints == ("её режут на куски", "её делят на всех")


def test_the_duration_is_taken_from_the_state() -> None:
    assert summarize(make_state()).duration == timedelta(minutes=6)


def test_an_unfinished_game_is_measured_against_the_clock() -> None:
    summary = summarize(make_state(finished_at=None, created_at=datetime.now(UTC)))

    assert timedelta() <= summary.duration < timedelta(minutes=1)


def test_a_clock_that_went_backwards_gives_no_negative_duration() -> None:
    summary = summarize(make_state(finished_at=STARTED_AT - timedelta(hours=1)))

    assert summary.duration == timedelta()


def test_the_case_number_is_empty_until_the_journal_gives_one() -> None:
    assert summarize(make_state()).case_number is None
    assert summarize(make_state(case_number=17)).case_number == 17


def test_the_summary_carries_the_ruleset_and_the_rounds() -> None:
    summary = summarize(make_state(ruleset=Ruleset.SUDDEN_DEATH))

    assert summary.ruleset is Ruleset.SUDDEN_DEATH
    assert summary.rounds == 3
    assert summary.players_count == 4
