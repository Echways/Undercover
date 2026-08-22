import logging
from typing import Protocol

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup

from undercover.bot.message_utils import Photo, show_or_advance_card
from undercover.game.models import GameMode, GameSessionState

logger = logging.getLogger(__name__)


class DiscussionBoard(Protocol):
    async def open_turn(
        self,
        bot: Bot,
        state: GameSessionState,
        photo: Photo,
        caption: str,
        keyboard: InlineKeyboardMarkup,
    ) -> int: ...

    async def close_turn(
        self,
        bot: Bot,
        state: GameSessionState,
        caption: str,
        keyboard: InlineKeyboardMarkup | None = None,
    ) -> None: ...


class SingleCardBoard:
    async def open_turn(
        self,
        bot: Bot,
        state: GameSessionState,
        photo: Photo,
        caption: str,
        keyboard: InlineKeyboardMarkup,
    ) -> int:
        message = await show_or_advance_card(
            bot, state.chat_id, state.current_message_id, photo, caption, keyboard
        )
        return message.message_id

    async def close_turn(
        self,
        bot: Bot,
        state: GameSessionState,
        caption: str,
        keyboard: InlineKeyboardMarkup | None = None,
    ) -> None:
        return None


class FeedBoard:
    async def open_turn(
        self,
        bot: Bot,
        state: GameSessionState,
        photo: Photo,
        caption: str,
        keyboard: InlineKeyboardMarkup,
    ) -> int:
        message = await bot.send_photo(state.chat_id, photo, caption=caption, reply_markup=keyboard)
        return message.message_id

    async def close_turn(
        self,
        bot: Bot,
        state: GameSessionState,
        caption: str,
        keyboard: InlineKeyboardMarkup | None = None,
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
            logger.info("ход %s не заморозился (%s)", state.current_message_id, error)


def board_for(state: GameSessionState) -> DiscussionBoard:
    return FeedBoard() if state.mode is GameMode.GROUP else SingleCardBoard()
