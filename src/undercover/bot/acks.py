from typing import Final

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from undercover.log import get_logger

logger = get_logger(__name__)

EXPIRED_QUERY_MARKERS: Final = ("query is too old", "query id is invalid")


def query_expired(error: BaseException) -> bool:
    if not isinstance(error, TelegramBadRequest):
        return False
    reason = error.message.lower()
    return any(marker in reason for marker in EXPIRED_QUERY_MARKERS)


async def ack(
    callback: CallbackQuery, text: str | None = None, *, show_alert: bool = False
) -> bool:
    try:
        await callback.answer(text, show_alert=show_alert)
    except TelegramBadRequest as error:
        if not query_expired(error):
            raise
        logger.info("callback.ack_expired", callback_data=callback.data, reason=error.message)
        return False
    return True
