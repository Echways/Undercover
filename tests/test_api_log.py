from typing import Any

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import (
    AnswerCallbackQuery,
    GetUpdates,
    SendMessage,
    SendPhoto,
    TelegramMethod,
)
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from conftest import entry, journal
from fake_bot import CHAT_ID, FakeSession, make_bot
from undercover.bot.middlewares.api_log import (
    TelegramApiLogMiddleware,
    describe_method,
    summarize,
)

BLOCKED = TelegramForbiddenError(
    method=SendPhoto(chat_id=1, photo="x"), message="bot was blocked by the user"
)


@pytest.fixture
def session() -> FakeSession:
    return FakeSession()


@pytest.fixture
def bot(session: FakeSession) -> Bot:
    return make_bot(session)


async def call(middleware: TelegramApiLogMiddleware, bot: Bot, method: TelegramMethod[Any]) -> Any:
    async def make_request(inner_bot: Bot, inner_method: TelegramMethod[Any]) -> Any:
        return await inner_bot.session.make_request(inner_bot, inner_method)

    return await middleware(make_request, bot, method)


async def test_a_rejected_call_names_the_method_and_the_reason(
    bot: Bot, session: FakeSession
) -> None:
    session.failures[SendPhoto] = BLOCKED

    with journal() as records, pytest.raises(TelegramForbiddenError):
        await call(TelegramApiLogMiddleware(), bot, SendPhoto(chat_id=42, photo="file-id"))

    rejected = entry(records, "telegram.rejected")
    assert rejected["method"] == "SendPhoto"
    assert rejected["arg_chat_id"] == 42
    assert rejected["error"] == "TelegramForbiddenError"
    assert "blocked" in rejected["reason"]
    assert rejected["duration_ms"] >= 0


async def test_a_flood_wait_is_visible_as_a_rejection(bot: Bot, session: FakeSession) -> None:
    session.failures[SendMessage] = TelegramRetryAfter(
        method=SendMessage(chat_id=CHAT_ID, text="."), message="Too Many Requests", retry_after=17
    )

    with journal() as records, pytest.raises(TelegramRetryAfter):
        await call(TelegramApiLogMiddleware(), bot, SendMessage(chat_id=CHAT_ID, text="."))

    assert entry(records, "telegram.rejected")["error"] == "TelegramRetryAfter"


async def test_a_successful_call_is_traced(bot: Bot) -> None:
    with journal() as records:
        await call(TelegramApiLogMiddleware(), bot, AnswerCallbackQuery(callback_query_id="cb-1"))

    assert entry(records, "telegram.done")["method"] == "AnswerCallbackQuery"


async def test_a_slow_call_is_promoted_to_a_warning(bot: Bot) -> None:
    with journal() as records:
        await call(
            TelegramApiLogMiddleware(slow_after=0.0),
            bot,
            AnswerCallbackQuery(callback_query_id="cb-1"),
        )

    assert entry(records, "telegram.slow")["log_level"] == "warning"


async def test_the_long_poll_is_never_called_slow(bot: Bot, session: FakeSession) -> None:
    session.results[GetUpdates] = [[]]

    with journal() as records:
        await call(TelegramApiLogMiddleware(slow_after=0.0), bot, GetUpdates(timeout=10))

    assert entry(records, "telegram.done")["method"] == "GetUpdates"


def test_the_arguments_are_shrunk_to_readable_size() -> None:
    described = describe_method(
        SendPhoto(
            chat_id=CHAT_ID,
            photo=BufferedInputFile(b"x" * 4096, filename="role_0.jpg"),
            caption="а" * 400,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="Играть", callback_data="play")]]
            ),
        )
    )

    assert described["method"] == "SendPhoto"
    assert described["arg_chat_id"] == CHAT_ID
    assert described["arg_photo"] == "<BufferedInputFile role_0.jpg>"
    assert described["arg_caption"] == f"{'а' * 160}…"
    assert described["arg_reply_markup"] == "<1 inline buttons>"


def test_unset_arguments_stay_out_of_the_log() -> None:
    described = describe_method(SendMessage(chat_id=CHAT_ID, text="привет"))

    assert set(described) == {"method", "arg_chat_id", "arg_text"}


def test_an_unknown_value_is_named_by_its_type() -> None:
    assert summarize(object()) == "<object>"
    assert summarize([1, 2, 3]) == "<3 items>"
