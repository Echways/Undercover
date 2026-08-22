import asyncio
import logging
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from functools import partial
from typing import Final

from aiogram import Bot, F, Router
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from undercover.bot.boards import board_for
from undercover.bot.guards import load_discussion
from undercover.bot.keyboards import button
from undercover.bot.message_utils import as_photo
from undercover.bot.turn_clock import OnExpire, Turn, TurnKeeper, TurnView, timed_caption
from undercover.game.engine import build_discussion_order
from undercover.game.models import GameSessionState, GameStatus
from undercover.media.card_renderer import CARD_SUFFIX, render_speaker_card
from undercover.redis.game_state import GameStateRepository
from undercover.texts import Buttons, Discussion, Errors, Timer
from undercover.utils.secure_random import secure_rng

logger = logging.getLogger(__name__)

BROKEN_ORDER: Final = "порядок высказываний испорчен"


class TalkAction(StrEnum):
    NEXT = "next"
    ROUND = "round"
    SPIES = "spies"


class TalkCB(CallbackData, prefix="talk"):
    action: TalkAction
    session_id: str
    cursor: int


def create_discussion_router(keeper: TurnKeeper) -> Router:
    router = Router(name="discussion")

    @router.callback_query(TalkCB.filter(F.action == TalkAction.NEXT))
    async def cb_next_speaker(
        callback: CallbackQuery,
        callback_data: TalkCB,
        games: GameStateRepository,
        bot: Bot,
    ) -> None:
        async with keeper.locks.held(callback_data.session_id):
            state = await load_discussion(callback, callback_data.session_id, games)
            if state is None:
                return
            if callback_data.cursor != state.discussion_cursor:
                await callback.answer(Errors.STALE_TURN, show_alert=True)
                return

            next_cursor = state.discussion_cursor + 1
            if next_cursor >= len(state.discussion_order):
                await callback.answer(Discussion.ALL_SPOKE, show_alert=True)
                return
            if _speaker_name(state, next_cursor) is None:
                await report_broken(callback, state)
                return

            await close_turn(bot, state, _spent(state))
            await open_turn(bot, games, state, next_cursor, keeper)
            await callback.answer()

    @router.callback_query(TalkCB.filter(F.action == TalkAction.ROUND))
    async def cb_another_round(
        callback: CallbackQuery,
        callback_data: TalkCB,
        games: GameStateRepository,
        bot: Bot,
    ) -> None:
        async with keeper.locks.held(callback_data.session_id):
            state = await load_discussion(callback, callback_data.session_id, games)
            if state is None:
                return
            if not _round_is_over(state, callback_data.cursor):
                await callback.answer(Errors.STALE_TURN, show_alert=True)
                return
            if _speaker_name(state, 0) is None:
                await report_broken(callback, state)
                return

            await close_turn(bot, state, _spent(state))
            state.discussion_round += 1
            await open_turn(bot, games, state, 0, keeper)
            await callback.answer()

    return router


async def start_discussion(
    bot: Bot, games: GameStateRepository, state: GameSessionState, keeper: TurnKeeper
) -> None:
    state.status = GameStatus.DISCUSSION
    state.discussion_order = build_discussion_order(state.players, secure_rng())
    await open_turn(bot, games, state, 0, keeper)


async def open_turn(
    bot: Bot,
    games: GameStateRepository,
    state: GameSessionState,
    cursor: int,
    keeper: TurnKeeper,
) -> None:
    name = state.players[state.discussion_order[cursor]].name
    is_last = cursor == len(state.discussion_order) - 1

    image = await asyncio.to_thread(render_speaker_card, name)
    keyboard = _speaker_keyboard(state, cursor, is_last)
    caption = speaker_caption(state, cursor)
    state.turn_deadline = _deadline(state)

    message_id = await board_for(state).open_turn(
        bot,
        state,
        as_photo(image, f"speaker_{cursor}.{CARD_SUFFIX}"),
        timed_caption(caption, state.turn_seconds, state.turn_seconds),
        keyboard,
    )

    state.discussion_cursor = cursor
    state.current_message_id = message_id
    await games.save(state)

    keeper.clock.start(
        bot,
        state,
        TurnView(caption=caption, keyboard=keyboard),
        expiry_handler(games, keeper),
    )


async def close_turn(
    bot: Bot,
    state: GameSessionState,
    marker: str,
    keyboard: InlineKeyboardMarkup | None = None,
) -> None:
    caption = speaker_caption(state, state.discussion_cursor)
    await board_for(state).close_turn(
        bot, state, f"{caption}\n{marker}" if marker else caption, keyboard
    )


def expiry_handler(games: GameStateRepository, keeper: TurnKeeper) -> OnExpire:
    return partial(_expire_turn, games, keeper)


async def report_broken(
    callback: CallbackQuery, state: GameSessionState, reason: str = BROKEN_ORDER
) -> None:
    await callback.answer(Errors.BROKEN_SESSION, show_alert=True)
    logger.error("партия %s: %s (%r)", state.session_id, reason, state.discussion_order)


def speaker_caption(state: GameSessionState, cursor: int) -> str:
    name = state.players[state.discussion_order[cursor]].name
    is_last = cursor == len(state.discussion_order) - 1
    body = (
        Discussion.LAST_TALK_CAPTION.format(name=name)
        if is_last
        else Discussion.TALK_CAPTION.format(
            position=cursor + 1, total=len(state.discussion_order), name=name
        )
    )
    return _round_prefix(state) + body


async def _expire_turn(
    games: GameStateRepository, keeper: TurnKeeper, bot: Bot, turn: Turn
) -> None:
    async with keeper.locks.held(turn.session_id):
        state = await games.load(turn.session_id)
        if state is None or state.status is not GameStatus.DISCUSSION:
            return
        if (state.discussion_round, state.discussion_cursor) != (turn.round, turn.cursor):
            return

        next_cursor = state.discussion_cursor + 1
        if next_cursor >= len(state.discussion_order):
            await close_turn(
                bot,
                state,
                Timer.EXPIRED,
                _speaker_keyboard(state, state.discussion_cursor, is_last=True),
            )
            return
        if _speaker_name(state, next_cursor) is None:
            logger.error(
                "партия %s: %s (%r)", state.session_id, BROKEN_ORDER, state.discussion_order
            )
            return

        await close_turn(bot, state, Timer.EXPIRED)
        await open_turn(bot, games, state, next_cursor, keeper)


def _deadline(state: GameSessionState) -> datetime | None:
    if state.turn_seconds <= 0:
        return None
    return datetime.now(UTC) + timedelta(seconds=state.turn_seconds)


def _spent(state: GameSessionState) -> str:
    if state.turn_seconds <= 0 or state.turn_deadline is None:
        return ""
    countdown = round((state.turn_deadline - datetime.now(UTC)).total_seconds())
    left = min(state.turn_seconds, max(0, countdown))
    return Timer.SPENT.format(seconds=state.turn_seconds - left)


def _speaker_name(state: GameSessionState, cursor: int) -> str | None:
    if not 0 <= cursor < len(state.discussion_order):
        return None
    order_index = state.discussion_order[cursor]
    if not 0 <= order_index < len(state.players):
        return None
    return state.players[order_index].name


def _round_is_over(state: GameSessionState, cursor: int) -> bool:
    return cursor == state.discussion_cursor == len(state.discussion_order) - 1


def _round_prefix(state: GameSessionState) -> str:
    if state.discussion_round == 1:
        return ""
    return Discussion.ROUND_PREFIX.format(round=state.discussion_round)


def _speaker_keyboard(state: GameSessionState, cursor: int, is_last: bool) -> InlineKeyboardMarkup:
    def talk_button(text: str, action: TalkAction) -> InlineKeyboardButton:
        return button(text, TalkCB(action=action, session_id=state.session_id, cursor=cursor))

    forward = (
        talk_button(Buttons.ANOTHER_ROUND, TalkAction.ROUND)
        if is_last
        else talk_button(Buttons.NEXT_SPEAKER, TalkAction.NEXT)
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[[forward], [talk_button(Buttons.SHOW_SPIES, TalkAction.SPIES)]]
    )
