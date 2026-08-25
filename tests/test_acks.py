import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery
from aiogram.types import CallbackQuery

from conftest import entry, journal
from fake_bot import FakeSession, callback_update, make_bot
from undercover.bot.acks import ack, query_expired

EXPIRED = TelegramBadRequest(
    method=AnswerCallbackQuery(callback_query_id="cb-1"),
    message="Bad Request: query is too old and response timeout expired or query ID is invalid",
)
SOMETHING_ELSE = TelegramBadRequest(
    method=AnswerCallbackQuery(callback_query_id="cb-1"),
    message="Bad Request: message text is empty",
)


@pytest.fixture
def session() -> FakeSession:
    return FakeSession()


@pytest.fixture
def bot(session: FakeSession) -> Bot:
    return make_bot(session)


def press(bot: Bot) -> CallbackQuery:
    query = callback_update("lobby:play").callback_query
    assert query is not None
    return query.as_(bot)


async def test_a_live_query_gets_its_answer(bot: Bot, session: FakeSession) -> None:
    answered = await ack(press(bot), "готово", show_alert=True)

    assert answered is True
    answers = session.calls(AnswerCallbackQuery)
    assert [answer.text for answer in answers] == ["готово"]
    assert answers[0].show_alert is True


async def test_an_expired_query_is_not_an_error(bot: Bot, session: FakeSession) -> None:
    session.failures[AnswerCallbackQuery] = EXPIRED

    with journal() as records:
        answered = await ack(press(bot))

    assert answered is False
    assert entry(records, "callback.ack_expired")["callback_data"] == "lobby:play"


async def test_any_other_rejection_still_escapes(bot: Bot, session: FakeSession) -> None:
    session.failures[AnswerCallbackQuery] = SOMETHING_ELSE

    with pytest.raises(TelegramBadRequest):
        await ack(press(bot))


def test_only_the_expired_query_is_recognised() -> None:
    assert query_expired(EXPIRED) is True
    assert query_expired(SOMETHING_ELSE) is False
    assert query_expired(RuntimeError("что угодно")) is False


async def test_ack_forwards_the_url_for_a_deep_link(bot: Bot, session: FakeSession) -> None:
    answered = await ack(press(bot), url="https://t.me/bot?start=join_1")

    assert answered is True
    answers = session.calls(AnswerCallbackQuery)
    assert [answer.url for answer in answers] == ["https://t.me/bot?start=join_1"]
