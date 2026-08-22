import asyncio
import logging
from enum import StrEnum
from typing import Final

from aiogram import Bot, F, Router
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from undercover.bot.boards import board_for
from undercover.bot.guards import load_discussion
from undercover.bot.keyboards import button
from undercover.bot.message_utils import as_photo
from undercover.game.engine import build_discussion_order
from undercover.game.models import GameSessionState, GameStatus
from undercover.media.card_renderer import CARD_SUFFIX, render_speaker_card
from undercover.redis.game_state import GameStateRepository
from undercover.texts import Buttons, Discussion, Errors
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


def create_discussion_router() -> Router:
    router = Router(name="discussion")

    @router.callback_query(TalkCB.filter(F.action == TalkAction.NEXT))
    async def cb_next_speaker(
        callback: CallbackQuery,
        callback_data: TalkCB,
        games: GameStateRepository,
        bot: Bot,
    ) -> None:
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

        await close_turn(bot, state)
        await open_turn(bot, games, state, next_cursor)
        await callback.answer()

    @router.callback_query(TalkCB.filter(F.action == TalkAction.ROUND))
    async def cb_another_round(
        callback: CallbackQuery,
        callback_data: TalkCB,
        games: GameStateRepository,
        bot: Bot,
    ) -> None:
        state = await load_discussion(callback, callback_data.session_id, games)
        if state is None:
            return
        if not _round_is_over(state, callback_data.cursor):
            await callback.answer(Errors.STALE_TURN, show_alert=True)
            return
        if _speaker_name(state, 0) is None:
            await report_broken(callback, state)
            return

        await close_turn(bot, state)
        state.discussion_round += 1
        await open_turn(bot, games, state, 0)
        await callback.answer()

    return router


async def start_discussion(bot: Bot, games: GameStateRepository, state: GameSessionState) -> None:
    state.status = GameStatus.DISCUSSION
    state.discussion_order = build_discussion_order(state.players, secure_rng())
    await open_turn(bot, games, state, 0)


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


async def close_turn(bot: Bot, state: GameSessionState) -> None:
    await board_for(state).close_turn(bot, state, speaker_caption(state, state.discussion_cursor))


async def open_turn(
    bot: Bot, games: GameStateRepository, state: GameSessionState, cursor: int
) -> None:
    name = state.players[state.discussion_order[cursor]].name
    is_last = cursor == len(state.discussion_order) - 1

    image = await asyncio.to_thread(render_speaker_card, name)

    message_id = await board_for(state).open_turn(
        bot,
        state,
        as_photo(image, f"speaker_{cursor}.{CARD_SUFFIX}"),
        speaker_caption(state, cursor),
        _speaker_keyboard(state, cursor, is_last),
    )

    state.discussion_cursor = cursor
    state.current_message_id = message_id
    await games.save(state)


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
