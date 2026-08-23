from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any, Final

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Chat, Message, TelegramObject, Update, User
from aiogram.types.update import UpdateTypeLookupError

from undercover.log import bind, get_logger, preview, unbind_all

logger = get_logger(__name__)

SLOW_UPDATE_SECONDS: Final = 3.0

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class UpdateLogMiddleware(BaseMiddleware):
    def __init__(self, slow_after: float = SLOW_UPDATE_SECONDS) -> None:
        self._slow_after = slow_after

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        context = describe_update(event) if isinstance(event, Update) else {}
        bind(**context)
        logger.info("update.received")
        started = monotonic()
        try:
            result = await handler(event, data)
        except Exception as error:
            logger.exception(
                "update.failed",
                duration_ms=_elapsed_ms(started),
                error=type(error).__name__,
                reason=str(error),
            )
            raise
        else:
            self._report_done(started)
            return result
        finally:
            unbind_all()

    def _report_done(self, started: float) -> None:
        elapsed = monotonic() - started
        if elapsed >= self._slow_after:
            logger.warning(
                "update.slow",
                duration_ms=round(elapsed * 1000),
                slow_after_ms=round(self._slow_after * 1000),
            )
            return
        logger.info("update.handled", duration_ms=round(elapsed * 1000))


def describe_update(update: Update) -> dict[str, Any]:
    context: dict[str, Any] = {"update_id": update.update_id, "update_type": _type_of(update)}
    event = _event_of(update)
    if event is None:
        return context

    user = _user_of(event)
    if user is not None:
        context["user_id"] = user.id
        context["user_name"] = user.username or user.full_name

    chat = _chat_of(event)
    if chat is not None:
        context["chat_id"] = chat.id
        context["chat_type"] = chat.type

    context.update(_payload_of(event))
    return context


def _payload_of(event: TelegramObject) -> dict[str, Any]:
    if isinstance(event, CallbackQuery):
        payload: dict[str, Any] = {"callback_data": event.data}
        if event.message is not None:
            payload["message_id"] = event.message.message_id
        return payload
    if isinstance(event, Message):
        return {"message_id": event.message_id, "text": preview(event.text or event.caption)}
    return {}


def _type_of(update: Update) -> str:
    try:
        return update.event_type
    except UpdateTypeLookupError:
        return "unknown"


def _event_of(update: Update) -> TelegramObject | None:
    try:
        return update.event
    except UpdateTypeLookupError:
        return None


def _user_of(event: TelegramObject) -> User | None:
    if isinstance(event, CallbackQuery):
        return event.from_user
    if isinstance(event, Message):
        return event.from_user
    return None


def _chat_of(event: TelegramObject) -> Chat | None:
    if isinstance(event, Message):
        return event.chat
    if isinstance(event, CallbackQuery):
        return None if event.message is None else event.message.chat
    return None


def _elapsed_ms(started: float) -> int:
    return round((monotonic() - started) * 1000)
