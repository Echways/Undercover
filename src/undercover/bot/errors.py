import logging

from aiogram import Router
from aiogram.types import CallbackQuery, ErrorEvent, Message, TelegramObject
from aiogram_dialog.api.exceptions import UnknownIntent, UnknownState

from undercover.texts import Errors

logger = logging.getLogger(__name__)

STALE_BUTTON_ERRORS = (UnknownIntent, UnknownState)


def create_error_router() -> Router:
    router = Router(name="errors")

    @router.errors()
    async def on_error(event: ErrorEvent) -> bool:
        if isinstance(event.exception, STALE_BUTTON_ERRORS):
            logger.info("нажата кнопка от прошлой партии: %s", event.exception)
            await _notify(event, Errors.STALE_BUTTON)
            return True

        logger.exception(
            "необработанная ошибка на апдейте %s",
            event.update.update_id,
            exc_info=event.exception,
        )
        await _notify(event, Errors.UNEXPECTED)
        return True

    return router


async def _notify(event: ErrorEvent, text: str) -> None:
    target = _target(event.update.event)
    if target is None:
        return
    try:
        if isinstance(target, CallbackQuery):
            await target.answer(text, show_alert=True)
        else:
            await target.answer(text)
    except Exception:
        logger.exception("не удалось сообщить об ошибке в чат")


def _target(event: TelegramObject) -> CallbackQuery | Message | None:
    if isinstance(event, (CallbackQuery, Message)):
        return event
    return None
