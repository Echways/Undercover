from aiogram import Router
from aiogram.types import CallbackQuery, ErrorEvent, Message, TelegramObject
from aiogram_dialog.api.exceptions import UnknownIntent, UnknownState

from undercover.bot.acks import ack, query_expired
from undercover.log import get_logger
from undercover.texts import Errors

logger = get_logger(__name__)

STALE_BUTTON_ERRORS = (UnknownIntent, UnknownState)


def create_error_router() -> Router:
    router = Router(name="errors")

    @router.errors()
    async def on_error(event: ErrorEvent) -> bool:
        error = event.exception
        if query_expired(error):
            logger.info("update.query_expired", reason=str(error))
            return True

        if isinstance(error, STALE_BUTTON_ERRORS):
            logger.info("update.stale_button", reason=str(error))
            await _notify(event, Errors.STALE_BUTTON)
            return True

        logger.exception("update.unhandled", error=type(error).__name__)
        await _notify(event, Errors.UNEXPECTED)
        return True

    return router


async def _notify(event: ErrorEvent, text: str) -> None:
    target = _target(event.update.event)
    if target is None:
        logger.info("update.unreported", reason="апдейт без чата")
        return
    try:
        if isinstance(target, CallbackQuery):
            await ack(target, text, show_alert=True)
        else:
            await target.answer(text)
    except Exception as error:
        logger.exception("update.report_failed", error=type(error).__name__)


def _target(event: TelegramObject) -> CallbackQuery | Message | None:
    if isinstance(event, (CallbackQuery, Message)):
        return event
    return None
