import asyncio
from datetime import UTC, datetime, timedelta
from typing import Final

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageCaption
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from fake_bot import CHAT_ID, FIRST_MESSAGE_ID, HOST_ID, FakeSession, make_bot
from undercover.bot.turn_clock import Turn, TurnClock, TurnView, timed_caption
from undercover.game.models import GameSessionState, GameStatus, PlayerState, Seating
from undercover.texts import countdown_line

SESSION_ID: Final = "11111111-1111-1111-1111-111111111111"
TICK: Final = timedelta(seconds=0.05)
VIEW: Final = TurnView(
    caption="Говорит: Аня",
    keyboard=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Дальше", callback_data="talk:next")]]
    ),
)


def make_state(seconds: float = 0.3, turn_seconds: int = 30) -> GameSessionState:
    return GameSessionState(
        session_id=SESSION_ID,
        chat_id=CHAT_ID,
        host_user_id=HOST_ID,
        seating=Seating.GROUP,
        status=GameStatus.DISCUSSION,
        players=[PlayerState(order_index=0, name="Аня", is_spy=True)],
        word_id=1,
        word_text="пицца",
        discussion_order=[0],
        current_message_id=FIRST_MESSAGE_ID,
        turn_seconds=turn_seconds,
        turn_deadline=datetime.now(UTC) + timedelta(seconds=seconds),
    )


class Expiries:
    def __init__(self) -> None:
        self.turns: list[Turn] = []
        self.done = asyncio.Event()

    async def __call__(self, bot: Bot, turn: Turn) -> None:
        self.turns.append(turn)
        self.done.set()


async def test_the_turn_expires_with_the_round_and_cursor_it_started_on() -> None:
    clock = TurnClock(tick=TICK)
    expiries = Expiries()
    state = make_state()
    state.discussion_round = 3
    state.discussion_cursor = 2

    clock.start(make_bot(FakeSession()), state, VIEW, expiries)
    await asyncio.wait_for(expiries.done.wait(), timeout=2)

    assert expiries.turns == [Turn(session_id=SESSION_ID, round=3, cursor=2)]


async def test_the_countdown_is_repainted_while_the_turn_runs() -> None:
    session = FakeSession()
    clock = TurnClock(tick=TICK)
    expiries = Expiries()

    clock.start(make_bot(session), make_state(), VIEW, expiries)
    await asyncio.wait_for(expiries.done.wait(), timeout=2)

    repaints = session.calls(EditMessageCaption)
    assert repaints
    assert all(call.reply_markup == VIEW.keyboard for call in repaints)
    assert all(VIEW.caption in (call.caption or "") for call in repaints)


async def test_a_finished_turn_is_forgotten_so_the_registry_does_not_grow() -> None:
    clock = TurnClock(tick=TICK)
    expiries = Expiries()

    clock.start(make_bot(FakeSession()), make_state(), VIEW, expiries)
    await asyncio.wait_for(expiries.done.wait(), timeout=2)
    await asyncio.sleep(0.05)

    assert clock.running == frozenset()


async def test_a_turn_without_a_timer_starts_no_task_at_all() -> None:
    session = FakeSession()
    clock = TurnClock(tick=TICK)
    state = make_state(turn_seconds=0)
    state.turn_deadline = None

    clock.start(make_bot(session), state, VIEW, Expiries())

    assert clock.running == frozenset()
    assert session.requests == []


async def test_starting_a_new_turn_cancels_the_previous_one() -> None:
    clock = TurnClock(tick=TICK)
    expiries = Expiries()
    bot = make_bot(FakeSession())

    clock.start(bot, make_state(seconds=5), VIEW, expiries)
    clock.start(bot, make_state(), VIEW, expiries)
    await asyncio.wait_for(expiries.done.wait(), timeout=2)
    await asyncio.sleep(0.1)

    assert expiries.turns == [Turn(session_id=SESSION_ID, round=1, cursor=0)]


async def test_stop_silences_the_clock() -> None:
    clock = TurnClock(tick=TICK)
    expiries = Expiries()

    clock.start(make_bot(FakeSession()), make_state(), VIEW, expiries)
    clock.stop(SESSION_ID)
    await asyncio.sleep(0.4)

    assert expiries.turns == []
    assert clock.running == frozenset()


async def test_stopping_a_turn_that_never_ran_is_harmless() -> None:
    TurnClock(tick=TICK).stop(SESSION_ID)


async def test_shutdown_leaves_nothing_running() -> None:
    clock = TurnClock(tick=TICK)

    clock.start(make_bot(FakeSession()), make_state(seconds=5), VIEW, Expiries())
    await clock.shutdown()

    assert clock.running == frozenset()


async def test_a_deleted_turn_message_does_not_stop_the_countdown() -> None:
    session = FakeSession()
    session.failures[EditMessageCaption] = TelegramBadRequest(
        method=EditMessageCaption(caption="x"), message="message to edit not found"
    )
    clock = TurnClock(tick=TICK)
    expiries = Expiries()

    clock.start(make_bot(session), make_state(), VIEW, expiries)
    await asyncio.wait_for(expiries.done.wait(), timeout=2)

    assert expiries.turns


async def test_a_turn_without_a_message_repaints_nothing() -> None:
    session = FakeSession()
    clock = TurnClock(tick=TICK)
    expiries = Expiries()
    state = make_state()
    state.current_message_id = None

    clock.start(make_bot(session), state, VIEW, expiries)
    await asyncio.wait_for(expiries.done.wait(), timeout=2)

    assert session.requests == []


def test_the_countdown_bar_empties_as_time_runs_out() -> None:
    full = countdown_line(60, 60)
    half = countdown_line(30, 60)
    empty = countdown_line(0, 60)

    assert full.count("█") > half.count("█") > empty.count("█")
    assert "60" in full
    assert "30" in half


def test_a_caption_without_a_timer_stays_untouched() -> None:
    assert timed_caption("Говорит: Аня", seconds_left=0, total=0) == "Говорит: Аня"


def test_a_timed_caption_carries_the_countdown_on_its_own_line() -> None:
    result = timed_caption("Говорит: Аня", seconds_left=30, total=60)

    assert result.startswith("Говорит: Аня\n")
    assert countdown_line(30, 60) in result


class SelfStopping:
    def __init__(self, clock: TurnClock) -> None:
        self._clock = clock
        self.finished = asyncio.Event()

    async def __call__(self, bot: Bot, turn: Turn) -> None:
        self._clock.stop(turn.session_id)
        await asyncio.sleep(0)
        self.finished.set()


async def test_an_expiring_turn_that_stops_the_clock_still_finishes_its_work() -> None:
    clock = TurnClock(tick=TICK)
    handler = SelfStopping(clock)

    clock.start(make_bot(FakeSession()), make_state(), VIEW, handler)
    await asyncio.wait_for(handler.finished.wait(), timeout=2)

    assert handler.finished.is_set()
    assert clock.running == frozenset()


async def test_stopping_a_clock_from_the_outside_still_cancels_it() -> None:
    clock = TurnClock(tick=TICK)
    expiries = Expiries()

    clock.start(make_bot(FakeSession()), make_state(seconds=5), VIEW, expiries)
    clock.stop(SESSION_ID)
    await asyncio.sleep(0.1)

    assert clock.running == frozenset()
    assert expiries.turns == []


async def test_a_turn_whose_deadline_has_already_passed_starts_no_countdown() -> None:
    session = FakeSession()
    clock = TurnClock(tick=TICK)
    expiries = Expiries()

    clock.start(make_bot(session), make_state(seconds=-1), VIEW, expiries)
    await asyncio.sleep(0.2)

    assert clock.running == frozenset()
    assert expiries.turns == [], "истёкшему ходу нечего отсчитывать"
    assert session.requests == []
