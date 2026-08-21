import asyncio
import logging
from collections.abc import Awaitable, Callable
from enum import StrEnum

from aiogram import Bot, F, Router
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardMarkup

from undercover.bot.guards import load_game_in_phase
from undercover.bot.keyboards import single_button
from undercover.bot.message_utils import as_photo, photo_file_id, show_or_advance_card
from undercover.texts import Buttons, Errors, Reveal
from undercover.game.models import GameSessionState, GameStatus, PlayerState
from undercover.media.card_renderer import (
    render_civilian_card,
    render_hidden_card,
    render_spy_card,
)
from undercover.redis.game_state import GameStateRepository

logger = logging.getLogger(__name__)

PhaseStarter = Callable[[Bot, GameStateRepository, GameSessionState], Awaitable[None]]


class RevealAction(StrEnum):
    SHOW = "show"
    NEXT = "next"


class RevealCB(CallbackData, prefix="reveal"):
    action: RevealAction
    session_id: str
    order_index: int


def create_reveal_router(start_discussion: PhaseStarter) -> Router:
    router = Router(name="reveal")

    @router.callback_query(RevealCB.filter(F.action == RevealAction.SHOW))
    async def cb_show_role(
        callback: CallbackQuery,
        callback_data: RevealCB,
        games: GameStateRepository,
        bot: Bot,
    ) -> None:
        turn = await _current_turn(callback, callback_data, games)
        if turn is None:
            return
        state, player = turn

        if player.has_viewed:
            await callback.answer(Reveal.ALREADY_VIEWED, show_alert=True)
            return
        if player.is_spy and player.order_index not in state.hint_by_spy:
            logger.error(
                "партия %s: шпиону %s не досталась подсказка",
                state.session_id,
                player.order_index,
            )
            await callback.answer(Errors.BROKEN_SESSION, show_alert=True)
            return

        is_last = state.reveal_cursor == len(state.players) - 1
        caption = (
            Reveal.LAST_VIEWED_CAPTION if is_last else Reveal.VIEWED_CAPTION
        ).format(name=player.name)
        image = await asyncio.to_thread(_render_role_card, player, state)

        message = await show_or_advance_card(
            bot,
            state.chat_id,
            state.current_message_id,
            as_photo(image, _card_filename(player.order_index)),
            caption,
            _keyboard(
                Buttons.START_DISCUSSION if is_last else Buttons.NEXT_PLAYER,
                RevealAction.NEXT,
                state,
            ),
        )

        player.has_viewed = True
        state.current_message_id = message.message_id
        await games.save(state)
        await callback.answer()

    @router.callback_query(RevealCB.filter(F.action == RevealAction.NEXT))
    async def cb_next_player(
        callback: CallbackQuery,
        callback_data: RevealCB,
        games: GameStateRepository,
        bot: Bot,
    ) -> None:
        turn = await _current_turn(callback, callback_data, games)
        if turn is None:
            return
        state, player = turn

        if not player.has_viewed:
            await callback.answer(Reveal.NOT_VIEWED_YET, show_alert=True)
            return

        if state.reveal_cursor == len(state.players) - 1:
            state.reveal_cursor = len(state.players)
            state.status = GameStatus.DISCUSSION
            await games.save(state)
            await start_discussion(bot, games, state)
            await callback.answer()
            return

        await _show_hidden_card(bot, games, state, state.reveal_cursor + 1)
        await callback.answer()

    return router


async def start_reveal(bot: Bot, games: GameStateRepository, state: GameSessionState) -> None:
    state.status = GameStatus.REVEAL
    state.reveal_cursor = 0
    await _show_hidden_card(bot, games, state, 0)


async def _show_hidden_card(
    bot: Bot, games: GameStateRepository, state: GameSessionState, order_index: int
) -> None:
    player = state.players[order_index]
    image = player.card_file_id or await asyncio.to_thread(render_hidden_card, player.name)

    message = await show_or_advance_card(
        bot,
        state.chat_id,
        state.current_message_id,
        as_photo(image, _card_filename(order_index)),
        Reveal.TURN_CAPTION.format(
            position=order_index + 1, total=len(state.players), name=player.name
        ),
        _keyboard(Buttons.SHOW_CARD, RevealAction.SHOW, state, order_index),
    )

    state.reveal_cursor = order_index
    state.current_message_id = message.message_id

    player.card_file_id = player.card_file_id or photo_file_id(message)
    await games.save(state)


async def _current_turn(
    callback: CallbackQuery, callback_data: RevealCB, games: GameStateRepository
) -> tuple[GameSessionState, PlayerState] | None:
    state = await load_game_in_phase(
        callback, callback_data.session_id, games, GameStatus.REVEAL, Reveal.WRONG_PHASE
    )
    if state is None:
        return None
    if callback_data.order_index != state.reveal_cursor:
        await callback.answer(Errors.STALE_TURN, show_alert=True)
        return None
    if not 0 <= state.reveal_cursor < len(state.players):
        logger.error(
            "партия %s: курсор раздачи %s вне списка из %s игроков",
            state.session_id,
            state.reveal_cursor,
            len(state.players),
        )
        await callback.answer(Errors.BROKEN_SESSION, show_alert=True)
        return None

    return state, state.players[state.reveal_cursor]


def _render_role_card(player: PlayerState, state: GameSessionState) -> bytes:
    if player.is_spy:
        return render_spy_card(player.name, state.hint_by_spy[player.order_index])
    return render_civilian_card(player.name, state.word_text)


def _card_filename(order_index: int) -> str:
    return f"card_{order_index}.png"


def _keyboard(
    text: str, action: RevealAction, state: GameSessionState, order_index: int | None = None
) -> InlineKeyboardMarkup:
    return single_button(
        text,
        RevealCB(
            action=action,
            session_id=state.session_id,
            order_index=state.reveal_cursor if order_index is None else order_index,
        ),
    )
