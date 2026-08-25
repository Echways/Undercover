from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from aiogram import Bot
from aiogram.types import CallbackQuery

from undercover.bot.acks import ack
from undercover.bot.turn_clock import TurnKeeper
from undercover.game.models import GameSessionState
from undercover.log import get_logger
from undercover.redis.game_state import GameStateRepository
from undercover.texts import Errors

logger = get_logger(__name__)

BROKEN_ORDER: Final = "порядок высказываний испорчен"

PhaseStarter = Callable[[Bot, GameStateRepository, GameSessionState], Awaitable[None]]

GameLogWriter = Callable[[GameSessionState], Awaitable[int]]


@dataclass(frozen=True, slots=True)
class TurnFlow:
    keeper: TurnKeeper
    start_voting: PhaseStarter


async def close_case(log_game: GameLogWriter, state: GameSessionState) -> None:
    if state.finished_at is None:
        state.finished_at = datetime.now(UTC)
    try:
        state.case_number = await log_game(state)
    except Exception as error:
        logger.exception(
            "game.log_failed",
            session_id=state.session_id,
            error=type(error).__name__,
        )


def log_broken_order(state: GameSessionState, reason: str = BROKEN_ORDER) -> None:
    logger.error(
        "discussion.broken_order",
        session_id=state.session_id,
        reason=reason,
        order=list(state.discussion_order),
    )


async def report_broken(
    callback: CallbackQuery, state: GameSessionState, reason: str = BROKEN_ORDER
) -> None:
    await ack(callback, Errors.BROKEN_SESSION, show_alert=True)
    log_broken_order(state, reason)
