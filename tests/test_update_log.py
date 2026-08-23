from typing import Any

import pytest
import structlog
from aiogram.types import TelegramObject, Update

from conftest import entry, events, journal
from fake_bot import CHAT_ID, HOST_ID, callback_update, message_update
from undercover.bot.middlewares.observability import UpdateLogMiddleware, describe_update

BOOM = RuntimeError("движок не завёлся")


async def run(
    middleware: UpdateLogMiddleware,
    update: Update,
    *,
    fail: bool = False,
    seen: list[dict[str, Any]] | None = None,
) -> None:
    async def handler(event: TelegramObject, data: dict[str, Any]) -> None:
        if seen is not None:
            seen.append(structlog.contextvars.get_contextvars())
        if fail:
            raise BOOM

    await middleware(handler, update, {})


async def test_a_press_is_narrated_from_arrival_to_finish() -> None:
    with journal() as records:
        await run(UpdateLogMiddleware(), callback_update("lobby:play", update_id=77))

    assert events(records) == ["update.received", "update.handled"]
    arrival = entry(records, "update.received")
    assert arrival["update_id"] == 77
    assert arrival["update_type"] == "callback_query"
    assert arrival["callback_data"] == "lobby:play"
    assert arrival["chat_id"] == CHAT_ID
    assert arrival["user_id"] == HOST_ID
    assert entry(records, "update.handled")["duration_ms"] >= 0


async def test_the_handler_sees_the_bound_context() -> None:
    seen: list[dict[str, Any]] = []

    await run(UpdateLogMiddleware(), message_update("/undercover"), seen=seen)

    assert seen[0]["chat_id"] == CHAT_ID
    assert seen[0]["update_type"] == "message"
    assert structlog.contextvars.get_contextvars() == {}


async def test_a_failure_is_logged_with_its_traceback_and_re_raised() -> None:
    with journal() as records, pytest.raises(RuntimeError):
        await run(UpdateLogMiddleware(), callback_update("lobby:play"), fail=True)

    failure = entry(records, "update.failed")
    assert failure["error"] == "RuntimeError"
    assert "движок не завёлся" in failure["reason"]
    assert "Traceback (most recent call last)" in failure["exception"]


async def test_a_slow_handler_is_flagged() -> None:
    with journal() as records:
        await run(UpdateLogMiddleware(slow_after=0.0), callback_update("lobby:play"))

    assert events(records) == ["update.received", "update.slow"]


def test_an_unknown_update_still_gets_a_line() -> None:
    assert describe_update(Update(update_id=5)) == {"update_id": 5, "update_type": "unknown"}


def test_a_long_message_is_trimmed() -> None:
    trimmed = describe_update(message_update("а" * 500))["text"]

    assert trimmed.endswith("…")
    assert len(trimmed) < 500
