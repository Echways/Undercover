from collections import OrderedDict
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any, Final

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject, User

from undercover.bot.acks import ack
from undercover.log import get_logger
from undercover.texts import Errors

logger = get_logger(__name__)

DEFAULT_INTERVAL: Final = 0.5


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(
        self,
        interval: float = DEFAULT_INTERVAL,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._interval = interval
        self._clock = clock
        self._seen: OrderedDict[int, float] = OrderedDict()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user is None or self._allow(user.id):
            return await handler(event, data)

        logger.debug("update.throttled", user_id=user.id)
        if isinstance(event, CallbackQuery):
            await ack(event, Errors.TOO_FAST)
        return None

    def _allow(self, user_id: int) -> bool:
        now = self._clock()
        self._forget_expired(now)

        last = self._seen.get(user_id)
        if last is not None and now - last < self._interval:
            return False

        self._seen[user_id] = now
        self._seen.move_to_end(user_id)
        return True

    def _forget_expired(self, now: float) -> None:
        while self._seen:
            user_id, last = next(iter(self._seen.items()))
            if now - last < self._interval:
                return
            del self._seen[user_id]
