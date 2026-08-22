import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup

from undercover.game.models import GameSessionState
from undercover.texts import countdown_line
from undercover.utils.keyed_locks import KeyedLocks

logger = logging.getLogger(__name__)

TICK: Final = timedelta(seconds=5)


@dataclass(frozen=True, slots=True)
class Turn:
    session_id: str
    round: int
    cursor: int


@dataclass(frozen=True, slots=True)
class TurnView:
    caption: str
    keyboard: InlineKeyboardMarkup


OnExpire = Callable[[Bot, Turn], Awaitable[None]]


def timed_caption(base: str, seconds_left: int, total: int) -> str:
    if total <= 0:
        return base
    return f"{base}\n{countdown_line(seconds_left, total)}"


class TurnClock:
    def __init__(self, tick: timedelta = TICK) -> None:
        self._tick = tick
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def start(self, bot: Bot, state: GameSessionState, view: TurnView, on_expire: OnExpire) -> None:
        self.stop(state.session_id)
        if state.turn_seconds <= 0 or state.turn_deadline is None:
            return

        session_id = state.session_id
        task = asyncio.create_task(self._run(bot, state.model_copy(deep=True), view, on_expire))
        self._tasks[session_id] = task
        task.add_done_callback(lambda finished: self._forget(session_id, finished))

    def stop(self, session_id: str) -> None:
        task = self._tasks.pop(session_id, None)
        if task is not None:
            task.cancel()

    async def shutdown(self) -> None:
        running = list(self._tasks.values())
        self._tasks.clear()
        for task in running:
            task.cancel()
        await asyncio.gather(*running, return_exceptions=True)

    @property
    def running(self) -> frozenset[str]:
        return frozenset(self._tasks)

    async def _run(
        self, bot: Bot, state: GameSessionState, view: TurnView, on_expire: OnExpire
    ) -> None:
        deadline = state.turn_deadline
        if deadline is None:
            return

        while True:
            left = deadline - datetime.now(UTC)
            if left <= timedelta(0):
                break
            await asyncio.sleep(min(self._tick, left).total_seconds())
            remaining = deadline - datetime.now(UTC)
            if remaining > timedelta(0):
                await self._repaint(bot, state, view, remaining)

        await on_expire(
            bot,
            Turn(
                session_id=state.session_id,
                round=state.discussion_round,
                cursor=state.discussion_cursor,
            ),
        )

    async def _repaint(
        self, bot: Bot, state: GameSessionState, view: TurnView, left: timedelta
    ) -> None:
        if state.current_message_id is None:
            return
        try:
            await bot.edit_message_caption(
                chat_id=state.chat_id,
                message_id=state.current_message_id,
                caption=timed_caption(view.caption, int(left.total_seconds()), state.turn_seconds),
                reply_markup=view.keyboard,
            )
        except TelegramAPIError as error:
            logger.info("отсчёт партии %s не перерисовался (%s)", state.session_id, error)

    def _forget(self, session_id: str, finished: asyncio.Task[None]) -> None:
        if self._tasks.get(session_id) is finished:
            del self._tasks[session_id]
        if not finished.cancelled() and finished.exception() is not None:
            logger.error("часовой партии %s упал", session_id, exc_info=finished.exception())


@dataclass(frozen=True, slots=True)
class TurnKeeper:
    clock: TurnClock
    locks: KeyedLocks
