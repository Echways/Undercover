import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
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
from undercover.bot.routers.reveal import PhaseStarter
from undercover.bot.turn_clock import OnExpire, Turn, TurnKeeper, TurnView, timed_caption
from undercover.game.engine import build_discussion_order, secure_rng
from undercover.game.models import Direction, DirectionBallot, GameSessionState, GameStatus
from undercover.game.voting import (
    alive,
    cast_direction,
    close_ballot,
    direction_result,
    open_direction_ballot,
    tally,
)
from undercover.log import get_logger
from undercover.media.card_renderer import CARD_SUFFIX, render_speaker_card
from undercover.redis.game_state import GameStateRepository
from undercover.texts import VOTE_REFUSALS, Buttons, Discussion, Errors, Timer, Vote

logger = get_logger(__name__)

BROKEN_ORDER: Final = "порядок высказываний испорчен"


class TalkAction(StrEnum):
    NEXT = "next"
    ROUND = "round"
    VOTE = "vote"
    SPIES = "spies"


class TalkCB(CallbackData, prefix="talk"):
    action: TalkAction
    session_id: str
    cursor: int


DIRECTIONS: Final[Mapping[TalkAction, Direction]] = {
    TalkAction.ROUND: Direction.ROUND,
    TalkAction.VOTE: Direction.VOTE,
}


@dataclass(frozen=True, slots=True)
class TurnFlow:
    keeper: TurnKeeper
    start_voting: PhaseStarter


def create_discussion_router(flow: TurnFlow) -> Router:
    router = Router(name="discussion")

    @router.callback_query(TalkCB.filter(F.action == TalkAction.NEXT))
    async def cb_next_speaker(
        callback: CallbackQuery,
        callback_data: TalkCB,
        games: GameStateRepository,
        bot: Bot,
    ) -> None:
        async with flow.keeper.locks.held(callback_data.session_id):
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

            await close_turn(bot, state, _spent(state), flow)
            await open_turn(bot, games, state, next_cursor, flow)
            await callback.answer()

    @router.callback_query(TalkCB.filter(F.action.in_(set(DIRECTIONS))))
    async def cb_direction(
        callback: CallbackQuery,
        callback_data: TalkCB,
        games: GameStateRepository,
        bot: Bot,
    ) -> None:
        async with flow.keeper.locks.held(callback_data.session_id):
            state = await load_discussion(callback, callback_data.session_id, games)
            if state is None:
                return
            if not _round_is_over(state, callback_data.cursor):
                await callback.answer(Errors.STALE_TURN, show_alert=True)
                return

            refusal = cast_direction(state, callback.from_user.id, DIRECTIONS[callback_data.action])
            if refusal is not None:
                await callback.answer(VOTE_REFUSALS[refusal], show_alert=True)
                return

            chosen = direction_result(state)
            if chosen is None:
                await games.save(state)
                await _recount(bot, games, state, flow)
                await callback.answer(Vote.COUNTED)
                return
            if _leads_nowhere(state, chosen):
                await report_broken(callback, state)
                return

            await follow_direction(bot, games, state, chosen, flow, _spent(state))
            await callback.answer()

    return router


async def start_discussion(
    bot: Bot, games: GameStateRepository, state: GameSessionState, flow: TurnFlow
) -> None:
    state.status = GameStatus.DISCUSSION
    state.discussion_order = build_discussion_order(alive(state), secure_rng())
    logger.info(
        "discussion.started",
        session_id=state.session_id,
        chat_id=state.chat_id,
        round=state.discussion_round,
        speakers=len(state.discussion_order),
    )
    await open_turn(bot, games, state, 0, flow)


async def open_turn(
    bot: Bot,
    games: GameStateRepository,
    state: GameSessionState,
    cursor: int,
    flow: TurnFlow,
) -> None:
    name = state.players[state.discussion_order[cursor]].name
    is_last = cursor == len(state.discussion_order) - 1

    if is_last:
        open_direction_ballot(state)
    else:
        close_ballot(state)

    image = await asyncio.to_thread(render_speaker_card, name)
    keyboard = _speaker_keyboard(state, cursor, is_last)
    caption = speaker_caption(state, cursor)
    state.turn_deadline = _deadline(state)

    message_id = await board_for(state).show(
        bot,
        state,
        as_photo(image, f"speaker_{cursor}.{CARD_SUFFIX}"),
        timed_caption(caption, state.turn_seconds, state.turn_seconds),
        keyboard,
    )

    state.discussion_cursor = cursor
    state.current_message_id = message_id
    await games.save(state)

    logger.info(
        "turn.opened",
        session_id=state.session_id,
        chat_id=state.chat_id,
        round=state.discussion_round,
        cursor=cursor,
        speaker=name,
        is_last=is_last,
        turn_seconds=state.turn_seconds,
    )
    _watch_turn(bot, games, state, caption, keyboard, flow)


async def close_turn(
    bot: Bot,
    state: GameSessionState,
    marker: str,
    flow: TurnFlow,
    keyboard: InlineKeyboardMarkup | None = None,
) -> None:
    flow.keeper.clock.stop(state.session_id)
    caption = speaker_caption(state, state.discussion_cursor)
    await board_for(state).revise(
        bot, state, f"{caption}\n{marker}" if marker else caption, keyboard
    )


async def follow_direction(
    bot: Bot,
    games: GameStateRepository,
    state: GameSessionState,
    chosen: Direction,
    flow: TurnFlow,
    marker: str,
) -> None:
    await close_turn(bot, state, marker, flow)
    if chosen is Direction.VOTE:
        await flow.start_voting(bot, games, state)
        return

    state.discussion_round += 1
    await open_turn(bot, games, state, 0, flow)


def expiry_handler(games: GameStateRepository, flow: TurnFlow) -> OnExpire:
    return partial(_expire_turn, games, flow)


async def report_broken(
    callback: CallbackQuery, state: GameSessionState, reason: str = BROKEN_ORDER
) -> None:
    await callback.answer(Errors.BROKEN_SESSION, show_alert=True)
    logger.error(
        "discussion.broken_order",
        session_id=state.session_id,
        reason=reason,
        order=list(state.discussion_order),
    )


def speaker_caption(state: GameSessionState, cursor: int) -> str:
    name = state.players[state.discussion_order[cursor]].name
    is_last = cursor == len(state.discussion_order) - 1
    if not is_last:
        body = Discussion.TALK_CAPTION.format(
            position=cursor + 1, total=len(state.discussion_order), name=name
        )
        return _round_prefix(state) + body

    body = Discussion.LAST_TALK_CAPTION.format(name=name)
    return _round_prefix(state) + body + f"\n{Vote.DIRECTION_PROMPT}" + _direction_tally(state)


async def _expire_turn(games: GameStateRepository, flow: TurnFlow, bot: Bot, turn: Turn) -> None:
    async with flow.keeper.locks.held(turn.session_id):
        state = await games.load(turn.session_id)
        if state is None or state.status is not GameStatus.DISCUSSION:
            return
        if (state.discussion_round, state.discussion_cursor) != (turn.round, turn.cursor):
            return

        logger.info(
            "turn.expired",
            session_id=state.session_id,
            chat_id=state.chat_id,
            round=turn.round,
            cursor=turn.cursor,
        )

        next_cursor = state.discussion_cursor + 1
        if next_cursor >= len(state.discussion_order):
            await close_turn(
                bot,
                state,
                Timer.EXPIRED,
                flow,
                _speaker_keyboard(state, state.discussion_cursor, is_last=True),
            )
            return
        if _speaker_name(state, next_cursor) is None:
            _report_broken_order(state)
            return

        await close_turn(bot, state, Timer.EXPIRED, flow)
        await open_turn(bot, games, state, next_cursor, flow)


async def _recount(
    bot: Bot, games: GameStateRepository, state: GameSessionState, flow: TurnFlow
) -> None:
    caption = speaker_caption(state, state.discussion_cursor)
    keyboard = _speaker_keyboard(state, state.discussion_cursor, is_last=True)
    await board_for(state).revise(
        bot, state, timed_caption(caption, _left(state), state.turn_seconds), keyboard
    )
    _watch_turn(bot, games, state, caption, keyboard, flow)


def _watch_turn(
    bot: Bot,
    games: GameStateRepository,
    state: GameSessionState,
    caption: str,
    keyboard: InlineKeyboardMarkup,
    flow: TurnFlow,
) -> None:
    flow.keeper.clock.start(
        bot,
        state,
        TurnView(caption=caption, keyboard=keyboard),
        expiry_handler(games, flow),
    )


def _report_broken_order(state: GameSessionState) -> None:
    logger.error(
        "discussion.broken_order",
        session_id=state.session_id,
        reason=BROKEN_ORDER,
        order=list(state.discussion_order),
    )


def _direction_tally(state: GameSessionState) -> str:
    ballot = state.ballot
    if not isinstance(ballot, DirectionBallot) or not ballot.votes:
        return ""
    counts = tally(ballot)
    return "\n" + Vote.DIRECTION_TALLY.format(
        round=counts[Direction.ROUND], vote=counts[Direction.VOTE]
    )


def _deadline(state: GameSessionState) -> datetime | None:
    if state.turn_seconds <= 0:
        return None
    return datetime.now(UTC) + timedelta(seconds=state.turn_seconds)


def _left(state: GameSessionState) -> int:
    if state.turn_seconds <= 0 or state.turn_deadline is None:
        return 0
    countdown = round((state.turn_deadline - datetime.now(UTC)).total_seconds())
    return min(state.turn_seconds, max(0, countdown))


def _spent(state: GameSessionState) -> str:
    if state.turn_seconds <= 0 or state.turn_deadline is None:
        return ""
    return Timer.SPENT.format(seconds=state.turn_seconds - _left(state))


def _speaker_name(state: GameSessionState, cursor: int) -> str | None:
    if not 0 <= cursor < len(state.discussion_order):
        return None
    order_index = state.discussion_order[cursor]
    if not 0 <= order_index < len(state.players):
        return None
    return state.players[order_index].name


def _leads_nowhere(state: GameSessionState, chosen: Direction) -> bool:
    return chosen is Direction.ROUND and _speaker_name(state, 0) is None


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
        [
            talk_button(Buttons.ANOTHER_ROUND, TalkAction.ROUND),
            talk_button(Buttons.GO_TO_VOTE, TalkAction.VOTE),
        ]
        if is_last
        else [talk_button(Buttons.NEXT_SPEAKER, TalkAction.NEXT)]
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[forward, [talk_button(Buttons.SHOW_SPIES, TalkAction.SPIES)]]
    )
