import logging
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import CallbackQuery, Message, PollAnswer, Update, User
from aiogram_dialog.api.exceptions import UnknownIntent
from fake_bot import FakeSession, callback_update, make_bot, message_update

from undercover.bot.errors import create_error_router
from undercover.texts import Errors

BOOM = RuntimeError("движок партии не завёлся")


@pytest.fixture
def session() -> FakeSession:
    return FakeSession()


@pytest.fixture
def bot(session: FakeSession) -> Bot:
    return make_bot(session)


def dispatcher_raising(error: Exception) -> Dispatcher:
    dispatcher = Dispatcher()

    @dispatcher.callback_query()
    async def on_callback(callback: CallbackQuery) -> None:
        raise error

    @dispatcher.message()
    async def on_message(message: Message) -> None:
        raise error

    dispatcher.include_router(create_error_router())
    return dispatcher


async def test_a_broken_press_gets_an_explanation(bot: Bot, session: FakeSession) -> None:
    await dispatcher_raising(BOOM).feed_update(bot, callback_update("press"))

    answers = session.calls(AnswerCallbackQuery)
    assert [answer.text for answer in answers] == [Errors.UNEXPECTED]
    assert answers[0].show_alert is True


async def test_a_broken_message_gets_an_explanation(bot: Bot, session: FakeSession) -> None:
    await dispatcher_raising(BOOM).feed_update(bot, message_update("Аня"))

    assert [sent.text for sent in session.calls(SendMessage)] == [Errors.UNEXPECTED]


async def test_the_traceback_reaches_the_log(
    bot: Bot, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="undercover.bot.errors"):
        await dispatcher_raising(BOOM).feed_update(bot, callback_update("press"))

    record = caplog.records[-1]
    assert record.exc_info is not None
    assert record.exc_info[1] is BOOM


async def test_a_stale_button_is_explained_without_a_traceback(
    bot: Bot, session: FakeSession, caplog: pytest.LogCaptureFixture
) -> None:
    stale = UnknownIntent("intent 42 не найден")
    with caplog.at_level(logging.INFO, logger="undercover.bot.errors"):
        await dispatcher_raising(stale).feed_update(bot, callback_update("press"))

    assert [answer.text for answer in session.calls(AnswerCallbackQuery)] == [
        Errors.STALE_BUTTON
    ]
    assert [record.levelno for record in caplog.records] == [logging.INFO]


async def test_a_failure_to_report_does_not_escape(bot: Bot, session: FakeSession) -> None:
    session.failures[AnswerCallbackQuery] = RuntimeError("Telegram недоступен")

    await dispatcher_raising(BOOM).feed_update(bot, callback_update("press"))


async def test_events_without_a_chat_are_only_logged(
    bot: Bot, session: FakeSession, caplog: pytest.LogCaptureFixture
) -> None:
    dispatcher = Dispatcher()

    @dispatcher.poll_answer()
    async def on_poll_answer(event: Any) -> None:
        raise BOOM

    dispatcher.include_router(create_error_router())

    with caplog.at_level(logging.ERROR, logger="undercover.bot.errors"):
        await dispatcher.feed_update(bot, _poll_answer_update())

    assert session.requests == []
    assert caplog.records[-1].exc_info is not None


def _poll_answer_update() -> Update:
    return Update(
        update_id=1,
        poll_answer=PollAnswer(
            poll_id="poll-1",
            user=User(id=777, is_bot=False, first_name="Ведущий"),
            option_ids=[0],
            option_persistent_ids=["0"],
        ),
    )
