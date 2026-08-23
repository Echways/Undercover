import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from enum import StrEnum

from aiogram import Bot, F, Router
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram_dialog import DialogManager, StartMode

from undercover.bot.boards import board_for
from undercover.bot.guards import deny_non_host, load_discussion, load_finished
from undercover.bot.keyboards import button
from undercover.bot.message_utils import as_photo
from undercover.bot.role_delivery import deliver_roles
from undercover.bot.routers.discussion import TalkAction, TalkCB, report_broken
from undercover.bot.routers.reveal import PhaseStarter, start_reveal
from undercover.bot.routers.setup_draft import Setup
from undercover.bot.turn_clock import TurnKeeper
from undercover.game.engine import (
    EmptyWordCatalogError,
    GameRulesError,
    WordsSourceFactory,
    create_session,
    secure_rng,
)
from undercover.game.models import GameMode, GameSessionState, GameStatus
from undercover.game.voting import misfired
from undercover.media.card_renderer import CARD_SUFFIX, render_result_card
from undercover.redis.game_state import GameStateRepository
from undercover.texts import Buttons, Discussion, Errors, Lobby, empty_catalog_text, win_line

logger = logging.getLogger(__name__)

GameLogWriter = Callable[[GameSessionState], Awaitable[None]]


class FinalAction(StrEnum):
    AGAIN = "again"
    NEW = "new"
    RESULT = "result"


class FinalCB(CallbackData, prefix="final"):
    action: FinalAction
    session_id: str


def create_finale_router(
    open_words: WordsSourceFactory,
    log_game: GameLogWriter,
    keeper: TurnKeeper,
    start_discussion: PhaseStarter,
) -> Router:
    router = Router(name="finale")

    @router.callback_query(TalkCB.filter(F.action == TalkAction.SPIES))
    async def cb_show_spies(
        callback: CallbackQuery,
        callback_data: TalkCB,
        games: GameStateRepository,
        bot: Bot,
    ) -> None:
        async with keeper.locks.held(callback_data.session_id):
            state = await load_discussion(callback, callback_data.session_id, games)
            if state is None or await deny_non_host(callback, state):
                return
            keeper.clock.stop(state.session_id)

            if not any(player.is_spy for player in state.players):
                await report_broken(callback, state, "в партии нет ни одного шпиона")
                return

            await show_final(bot, games, state)
            await write_log(log_game, state)
            await callback.answer()

    @router.callback_query(FinalCB.filter(F.action == FinalAction.RESULT))
    async def cb_show_result(
        callback: CallbackQuery,
        callback_data: FinalCB,
        games: GameStateRepository,
        bot: Bot,
    ) -> None:
        state = await load_finished(callback, callback_data.session_id, games)
        if state is None:
            return

        await show_final(bot, games, state)
        await callback.answer()

    @router.callback_query(FinalCB.filter(F.action == FinalAction.AGAIN))
    async def cb_play_again(
        callback: CallbackQuery,
        callback_data: FinalCB,
        games: GameStateRepository,
        bot: Bot,
    ) -> None:
        state = await load_finished(callback, callback_data.session_id, games)
        if state is None:
            return
        keeper.clock.stop(state.session_id)

        try:
            async with open_words() as words:
                fresh = await create_session(
                    chat_id=state.chat_id,
                    host_user_id=state.host_user_id,
                    player_names=[player.name for player in state.players],
                    player_ids=_telegram_ids(state),
                    spies_count=sum(player.is_spy for player in state.players),
                    words=words,
                    rng=secure_rng(),
                    category_ids=state.category_ids,
                    mode=state.mode,
                    ruleset=state.ruleset,
                    turn_seconds=state.turn_seconds,
                )
        except EmptyWordCatalogError:
            logger.exception("партия %s: следующую не собрать, словарь пуст", state.session_id)
            await callback.answer(empty_catalog_text(state.category_ids), show_alert=True)
            return
        except GameRulesError:
            logger.exception("партия %s: её состав больше не по правилам", state.session_id)
            await callback.answer(Errors.BROKEN_SESSION, show_alert=True)
            return

        if fresh.mode is GameMode.GROUP:
            if await deliver_roles(bot, fresh):
                await callback.answer(Lobby.DELIVERY_FAILED, show_alert=True)
                return
            await _replace(games, state, fresh)
            await start_discussion(bot, games, fresh)
        else:
            _carry_over_cards(state, fresh)
            await _replace(games, state, fresh)
            await start_reveal(bot, games, fresh)

        await callback.answer()

    @router.callback_query(FinalCB.filter(F.action == FinalAction.NEW))
    async def cb_new_game(
        callback: CallbackQuery,
        callback_data: FinalCB,
        games: GameStateRepository,
        dialog_manager: DialogManager,
    ) -> None:
        state = await load_finished(callback, callback_data.session_id, games)
        if state is None:
            return

        keeper.clock.stop(state.session_id)
        await games.delete(state.session_id)
        await dialog_manager.start(Setup.ask_players_count, mode=StartMode.RESET_STACK)
        await callback.answer()

    return router


async def show_final(bot: Bot, games: GameStateRepository, state: GameSessionState) -> None:
    spies = [player.name for player in state.players if player.is_spy]
    image = await asyncio.to_thread(render_result_card, spies, state.word_text, state.winner)

    state.current_message_id = await board_for(state).show(
        bot,
        state,
        as_photo(image, f"result.{CARD_SUFFIX}"),
        _final_caption(state, spies),
        _final_keyboard(state),
    )
    state.status = GameStatus.FINISHED
    await games.save(state)


async def write_log(log_game: GameLogWriter, state: GameSessionState) -> None:
    try:
        await log_game(state)
    except Exception:
        logger.exception("партия %s: не записалась в журнал", state.session_id)


def _final_caption(state: GameSessionState, spies: Sequence[str]) -> str:
    body = Discussion.FINAL_CAPTION.format(
        title=(Discussion.SPY_TITLE_MANY if len(spies) > 1 else Discussion.SPY_TITLE_ONE),
        spies=", ".join(spies),
        word=state.word_text,
    )
    if state.winner is None:
        return body
    return f"{win_line(state.winner, misfire=misfired(state))}\n{body}"


async def _replace(
    games: GameStateRepository, previous: GameSessionState, fresh: GameSessionState
) -> None:
    await games.save(fresh)
    await games.delete(previous.session_id)


def _carry_over_cards(previous: GameSessionState, fresh: GameSessionState) -> None:
    fresh.current_message_id = previous.current_message_id
    for player, dealt_before in zip(fresh.players, previous.players, strict=True):
        player.card_file_id = dealt_before.card_file_id


def _telegram_ids(state: GameSessionState) -> list[int] | None:
    known = [player.user_id for player in state.players if player.user_id is not None]
    return known if len(known) == len(state.players) else None


def _final_keyboard(state: GameSessionState) -> InlineKeyboardMarkup:
    def final_button(text: str, action: FinalAction) -> InlineKeyboardButton:
        return button(text, FinalCB(action=action, session_id=state.session_id))

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [final_button(Buttons.PLAY_AGAIN, FinalAction.AGAIN)],
            [final_button(Buttons.NEW_GAME, FinalAction.NEW)],
        ]
    )
