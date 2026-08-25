from typing import Protocol

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup

from undercover.bot.message_utils import Photo, show_or_advance_card
from undercover.game.models import GameSessionState, Seating
from undercover.log import get_logger

logger = get_logger(__name__)


class PhaseBoard(Protocol):
    async def show(
        self,
        bot: Bot,
        state: GameSessionState,
        photo: Photo,
        caption: str,
        keyboard: InlineKeyboardMarkup,
        /,
    ) -> int: ...

    async def revise(
        self,
        bot: Bot,
        state: GameSessionState,
        caption: str,
        keyboard: InlineKeyboardMarkup | None = None,
        /,
    ) -> None: ...


class SingleCardBoard:
    async def show(
        self,
        bot: Bot,
        state: GameSessionState,
        photo: Photo,
        caption: str,
        keyboard: InlineKeyboardMarkup,
        /,
    ) -> int:
        message = await show_or_advance_card(
            bot, state.chat_id, state.current_message_id, photo, caption, keyboard
        )
        return message.message_id

    async def revise(
        self,
        _bot: Bot,
        _state: GameSessionState,
        _caption: str,
        _keyboard: InlineKeyboardMarkup | None = None,
        /,
    ) -> None:
        return None


class FeedBoard:
    async def show(
        self,
        bot: Bot,
        state: GameSessionState,
        photo: Photo,
        caption: str,
        keyboard: InlineKeyboardMarkup,
        /,
    ) -> int:
        message = await bot.send_photo(state.chat_id, photo, caption=caption, reply_markup=keyboard)
        return message.message_id

    async def revise(
        self,
        bot: Bot,
        state: GameSessionState,
        caption: str,
        keyboard: InlineKeyboardMarkup | None = None,
        /,
    ) -> None:
        if state.current_message_id is None:
            return
        try:
            await bot.edit_message_caption(
                chat_id=state.chat_id,
                message_id=state.current_message_id,
                caption=caption,
                reply_markup=keyboard,
            )
        except TelegramBadRequest as error:
            logger.info(
                "board.freeze_failed",
                message_id=state.current_message_id,
                reason=str(error),
            )


def board_for(state: GameSessionState) -> PhaseBoard:
    return FeedBoard() if state.seating is Seating.GROUP else SingleCardBoard()
