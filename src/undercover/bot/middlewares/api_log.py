from time import monotonic
from typing import Any, Final

from aiogram import Bot
from aiogram.client.session.middlewares.base import (
    BaseRequestMiddleware,
    NextRequestMiddlewareType,
)
from aiogram.exceptions import TelegramAPIError
from aiogram.methods import Response, TelegramMethod
from aiogram.methods.base import TelegramType
from aiogram.types import InlineKeyboardMarkup, InputFile, ReplyKeyboardMarkup

from undercover.log import get_logger, preview

logger = get_logger(__name__)

SLOW_CALL_SECONDS: Final = 2.0

LONG_POLL_METHODS: Final = frozenset({"GetUpdates"})

Scalar = str | int | float | bool | None


class TelegramApiLogMiddleware(BaseRequestMiddleware):
    def __init__(self, slow_after: float = SLOW_CALL_SECONDS) -> None:
        self._slow_after = slow_after

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method: TelegramMethod[TelegramType],
    ) -> Response[TelegramType]:
        call = describe_method(method)
        logger.debug("telegram.request", **call)
        started = monotonic()
        try:
            response = await make_request(bot, method)
        except TelegramAPIError as error:
            logger.warning(
                "telegram.rejected",
                **call,
                duration_ms=_elapsed_ms(started),
                error=type(error).__name__,
                reason=str(error),
            )
            raise
        except Exception as error:
            logger.exception(
                "telegram.broken",
                **call,
                duration_ms=_elapsed_ms(started),
                error=type(error).__name__,
            )
            raise
        self._report_done(call, started)
        return response

    def _report_done(self, call: dict[str, Scalar], started: float) -> None:
        elapsed = monotonic() - started
        if elapsed >= self._slow_after and call["method"] not in LONG_POLL_METHODS:
            logger.warning("telegram.slow", **call, duration_ms=round(elapsed * 1000))
            return
        logger.debug("telegram.done", **call, duration_ms=round(elapsed * 1000))


def describe_method(method: TelegramMethod[Any]) -> dict[str, Scalar]:
    call: dict[str, Scalar] = {"method": type(method).__name__}
    for name in sorted(method.model_fields_set):
        value = getattr(method, name, None)
        if value is not None:
            call[f"arg_{name}"] = summarize(value)
    return call


def summarize(value: object) -> Scalar:
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return preview(value)
    if isinstance(value, InputFile):
        return f"<{type(value).__name__} {value.filename}>"
    if isinstance(value, InlineKeyboardMarkup):
        return f"<{_button_count(value.inline_keyboard)} inline buttons>"
    if isinstance(value, ReplyKeyboardMarkup):
        return f"<{_button_count(value.keyboard)} reply buttons>"
    if isinstance(value, list | tuple):
        return f"<{len(value)} items>"
    return f"<{type(value).__name__}>"


def _button_count(rows: list[list[Any]]) -> int:
    return sum(len(row) for row in rows)


def _elapsed_ms(started: float) -> int:
    return round((monotonic() - started) * 1000)
