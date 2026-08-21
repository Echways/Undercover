import asyncio
import logging
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Final

from aiogram import Bot, F, Router
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram_dialog import DialogManager, StartMode

from undercover.bot.guards import load_game_in_phase
from undercover.bot.keyboards import button
from undercover.bot.message_utils import as_photo, show_or_advance_card
from undercover.bot.routers.reveal import start_reveal
from undercover.bot.routers.setup_dialog import Setup, WordsSourceFactory
from undercover.game.engine import (
    EmptyWordCatalogError,
    GameRulesError,
    build_discussion_order,
    create_session,
)
from undercover.game.models import GameSessionState, GameStatus
from undercover.media.card_renderer import (
    CARD_SUFFIX,
    render_result_card,
    render_speaker_card,
)
from undercover.redis.game_state import GameStateRepository
from undercover.texts import Buttons, Discussion, Errors, empty_catalog_text
from undercover.utils.secure_random import secure_rng

logger = logging.getLogger(__name__)

GameLogWriter = Callable[[GameSessionState], Awaitable[None]]

BROKEN_ORDER: Final = "порядок высказываний испорчен"


class TalkAction(StrEnum):
    NEXT = "next"
    ROUND = "round"
    SPIES = "spies"


class TalkCB(CallbackData, prefix="talk"):
    action: TalkAction
    session_id: str
    cursor: int


class FinalAction(StrEnum):
    AGAIN = "again"
    NEW = "new"


class FinalCB(CallbackData, prefix="final"):
    action: FinalAction
    session_id: str


def create_discussion_router(open_words: WordsSourceFactory, log_game: GameLogWriter) -> Router:
    router = Router(name="discussion")

    @router.callback_query(TalkCB.filter(F.action == TalkAction.NEXT))
    async def cb_next_speaker(
        callback: CallbackQuery,
        callback_data: TalkCB,
        games: GameStateRepository,
        bot: Bot,
    ) -> None:
        state = await _in_discussion(callback, callback_data.session_id, games)
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
            await _report_broken(callback, state)
            return

        await _show_speaker(bot, games, state, next_cursor)
        await callback.answer()

    @router.callback_query(TalkCB.filter(F.action == TalkAction.ROUND))
    async def cb_another_round(
        callback: CallbackQuery,
        callback_data: TalkCB,
        games: GameStateRepository,
        bot: Bot,
    ) -> None:
        state = await _in_discussion(callback, callback_data.session_id, games)
        if state is None:
            return
        if not _round_is_over(state, callback_data.cursor):
            await callback.answer(Errors.STALE_TURN, show_alert=True)
            return
        if _speaker_name(state, 0) is None:
            await _report_broken(callback, state)
            return

        state.discussion_round += 1
        await _show_speaker(bot, games, state, 0)
        await callback.answer()

    @router.callback_query(TalkCB.filter(F.action == TalkAction.SPIES))
    async def cb_show_spies(
        callback: CallbackQuery,
        callback_data: TalkCB,
        games: GameStateRepository,
        bot: Bot,
    ) -> None:
        state = await _in_discussion(callback, callback_data.session_id, games)
        if state is None:
            return

        spies = [player.name for player in state.players if player.is_spy]
        if not spies:
            await _report_broken(callback, state, "в партии нет ни одного шпиона")
            return

        image = await asyncio.to_thread(render_result_card, spies, state.word_text)
        message = await show_or_advance_card(
            bot,
            state.chat_id,
            state.current_message_id,
            as_photo(image, f"result.{CARD_SUFFIX}"),
            Discussion.FINAL_CAPTION.format(
                title=(Discussion.SPY_TITLE_MANY if len(spies) > 1 else Discussion.SPY_TITLE_ONE),
                spies=", ".join(spies),
                word=state.word_text,
            ),
            _final_keyboard(state),
        )

        state.status = GameStatus.FINISHED
        state.current_message_id = message.message_id
        await games.save(state)
        await _write_log(log_game, state)
        await callback.answer()

    @router.callback_query(FinalCB.filter(F.action == FinalAction.AGAIN))
    async def cb_play_again(
        callback: CallbackQuery,
        callback_data: FinalCB,
        games: GameStateRepository,
        bot: Bot,
    ) -> None:
        state = await _finished_game(callback, callback_data.session_id, games)
        if state is None:
            return

        try:
            async with open_words() as words:
                fresh = await create_session(
                    chat_id=state.chat_id,
                    host_user_id=state.host_user_id,
                    player_names=[player.name for player in state.players],
                    spies_count=sum(player.is_spy for player in state.players),
                    words=words,
                    rng=secure_rng(),
                    category_ids=state.category_ids,
                )
        except EmptyWordCatalogError:
            logger.exception("партия %s: следующую не собрать, словарь пуст", state.session_id)
            await callback.answer(empty_catalog_text(state.category_ids), show_alert=True)
            return
        except GameRulesError:
            logger.exception("партия %s: её состав больше не по правилам", state.session_id)
            await callback.answer(Errors.BROKEN_SESSION, show_alert=True)
            return

        fresh.current_message_id = state.current_message_id
        for player, previous in zip(fresh.players, state.players, strict=True):
            player.card_file_id = previous.card_file_id

        await games.save(fresh)

        await games.delete(state.session_id)
        await start_reveal(bot, games, fresh)
        await callback.answer()

    @router.callback_query(FinalCB.filter(F.action == FinalAction.NEW))
    async def cb_new_game(
        callback: CallbackQuery,
        callback_data: FinalCB,
        games: GameStateRepository,
        dialog_manager: DialogManager,
    ) -> None:
        state = await _finished_game(callback, callback_data.session_id, games)
        if state is None:
            return

        await games.delete(state.session_id)
        await dialog_manager.start(Setup.ask_players_count, mode=StartMode.RESET_STACK)
        await callback.answer()

    return router


async def start_discussion(bot: Bot, games: GameStateRepository, state: GameSessionState) -> None:
    state.status = GameStatus.DISCUSSION
    state.discussion_order = build_discussion_order(state.players, secure_rng())
    await _show_speaker(bot, games, state, 0)


async def _show_speaker(
    bot: Bot, games: GameStateRepository, state: GameSessionState, cursor: int
) -> None:
    name = state.players[state.discussion_order[cursor]].name
    is_last = cursor == len(state.discussion_order) - 1

    image = await asyncio.to_thread(render_speaker_card, name)

    message = await show_or_advance_card(
        bot,
        state.chat_id,
        state.current_message_id,
        as_photo(image, f"speaker_{cursor}.{CARD_SUFFIX}"),
        _round_prefix(state)
        + (
            Discussion.LAST_TALK_CAPTION.format(name=name)
            if is_last
            else Discussion.TALK_CAPTION.format(
                position=cursor + 1, total=len(state.discussion_order), name=name
            )
        ),
        _speaker_keyboard(state, cursor, is_last),
    )

    state.discussion_cursor = cursor
    state.current_message_id = message.message_id
    await games.save(state)


async def _in_discussion(
    callback: CallbackQuery, session_id: str, games: GameStateRepository
) -> GameSessionState | None:
    return await load_game_in_phase(
        callback, session_id, games, GameStatus.DISCUSSION, Discussion.WRONG_PHASE
    )


async def _finished_game(
    callback: CallbackQuery, session_id: str, games: GameStateRepository
) -> GameSessionState | None:
    return await load_game_in_phase(
        callback, session_id, games, GameStatus.FINISHED, Discussion.GAME_IS_ON
    )


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


async def _report_broken(
    callback: CallbackQuery, state: GameSessionState, reason: str = BROKEN_ORDER
) -> None:
    await callback.answer(Errors.BROKEN_SESSION, show_alert=True)
    logger.error("партия %s: %s (%r)", state.session_id, reason, state.discussion_order)


async def _write_log(log_game: GameLogWriter, state: GameSessionState) -> None:
    try:
        await log_game(state)
    except Exception:
        logger.exception("партия %s: не записалась в журнал", state.session_id)


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


def _final_keyboard(state: GameSessionState) -> InlineKeyboardMarkup:
    def final_button(text: str, action: FinalAction) -> InlineKeyboardButton:
        return button(text, FinalCB(action=action, session_id=state.session_id))

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [final_button(Buttons.PLAY_AGAIN, FinalAction.AGAIN)],
            [final_button(Buttons.NEW_GAME, FinalAction.NEW)],
        ]
    )
