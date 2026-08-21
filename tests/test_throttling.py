from typing import Any, Final

import pytest
from aiogram import Bot, Dispatcher
from aiogram.methods import AnswerCallbackQuery

from fake_bot import HOST_ID, FakeSession, callback_update, make_bot, message_update
from undercover.bot.middlewares.throttling import ThrottlingMiddleware
from undercover.texts import Errors

INTERVAL: Final = 0.5
OTHER_USER: Final = HOST_ID + 1


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def middleware(clock: FakeClock) -> ThrottlingMiddleware:
    return ThrottlingMiddleware(interval=INTERVAL, clock=clock)


@pytest.fixture
def session() -> FakeSession:
    return FakeSession()


@pytest.fixture
def bot(session: FakeSession) -> Bot:
    return make_bot(session)


@pytest.fixture
def handled() -> list[int]:
    return []


@pytest.fixture
def dispatcher(middleware: ThrottlingMiddleware, handled: list[int]) -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.message.outer_middleware(middleware)
    dispatcher.callback_query.outer_middleware(middleware)

    @dispatcher.message()
    async def on_message(message: Any) -> None:
        handled.append(message.message_id)

    @dispatcher.callback_query()
    async def on_callback(callback: Any) -> None:
        handled.append(callback.message.message_id)
        await callback.answer()

    return dispatcher


async def test_the_first_press_goes_through(
    dispatcher: Dispatcher, bot: Bot, handled: list[int]
) -> None:
    await dispatcher.feed_update(bot, callback_update("press", update_id=1))

    assert len(handled) == 1


async def test_a_hasty_second_press_is_dropped(
    dispatcher: Dispatcher, bot: Bot, clock: FakeClock, handled: list[int]
) -> None:
    await dispatcher.feed_update(bot, callback_update("press", update_id=1))
    clock.advance(INTERVAL / 2)
    await dispatcher.feed_update(bot, callback_update("press", update_id=2))

    assert len(handled) == 1


async def test_a_dropped_press_is_answered_so_the_button_stops_spinning(
    dispatcher: Dispatcher, bot: Bot, session: FakeSession, clock: FakeClock
) -> None:
    await dispatcher.feed_update(bot, callback_update("press", update_id=1))
    clock.advance(INTERVAL / 2)
    await dispatcher.feed_update(bot, callback_update("press", update_id=2))

    answers = session.calls(AnswerCallbackQuery)
    assert [answer.text for answer in answers] == [None, Errors.TOO_FAST]


async def test_the_next_press_goes_through_once_the_interval_has_passed(
    dispatcher: Dispatcher, bot: Bot, clock: FakeClock, handled: list[int]
) -> None:
    await dispatcher.feed_update(bot, callback_update("press", update_id=1))
    clock.advance(INTERVAL)
    await dispatcher.feed_update(bot, callback_update("press", update_id=2))

    assert len(handled) == 2


async def test_players_do_not_throttle_each_other(
    dispatcher: Dispatcher, bot: Bot, handled: list[int]
) -> None:
    await dispatcher.feed_update(bot, callback_update("press", update_id=1))
    await dispatcher.feed_update(bot, callback_update("press", update_id=2, user_id=OTHER_USER))

    assert len(handled) == 2


async def test_messages_and_presses_share_one_limit(
    dispatcher: Dispatcher, bot: Bot, clock: FakeClock, handled: list[int]
) -> None:
    await dispatcher.feed_update(bot, message_update("Аня", update_id=1))
    clock.advance(INTERVAL / 2)
    await dispatcher.feed_update(bot, callback_update("press", update_id=2))

    assert len(handled) == 1


async def test_a_dropped_message_gets_no_reply(
    dispatcher: Dispatcher, bot: Bot, session: FakeSession, clock: FakeClock
) -> None:
    await dispatcher.feed_update(bot, message_update("Аня", update_id=1))
    clock.advance(INTERVAL / 2)
    await dispatcher.feed_update(bot, message_update("Аня", update_id=2))

    assert session.requests == []


async def test_forgotten_users_do_not_pile_up(
    middleware: ThrottlingMiddleware, clock: FakeClock
) -> None:
    for user_id in range(100):
        middleware._allow(user_id)
    clock.advance(INTERVAL)
    middleware._allow(HOST_ID)

    assert list(middleware._seen) == [HOST_ID]
