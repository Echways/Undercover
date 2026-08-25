from typing import Final

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    BufferedInputFile,
    InlineKeyboardMarkup,
    InputFile,
    InputMediaPhoto,
    Message,
)

from undercover.log import get_logger

logger = get_logger(__name__)

Photo = InputFile | str

NOT_MODIFIED: Final = "message is not modified"


async def show_or_advance_card(
    bot: Bot,
    chat_id: int,
    message_id: int | None,
    photo: Photo,
    caption: str,
    keyboard: InlineKeyboardMarkup | None = None,
) -> Message:
    if message_id is None:
        return await _send_card(bot, chat_id, photo, caption, keyboard)

    try:
        edited = await bot.edit_message_media(
            chat_id=chat_id,
            message_id=message_id,
            media=InputMediaPhoto(media=photo, caption=caption),
            reply_markup=keyboard,
        )
    except TelegramBadRequest as error:
        logger.info("message.edit_failed", message_id=message_id, reason=str(error))
    else:
        if isinstance(edited, Message):
            return edited
        logger.warning("message.edit_returned_flag", result=repr(edited))

    await _delete_quietly(bot, chat_id, message_id)
    return await _send_card(bot, chat_id, photo, caption, keyboard)


async def show_or_resend_text(
    bot: Bot,
    chat_id: int,
    message_id: int | None,
    text: str,
    keyboard: InlineKeyboardMarkup | None = None,
) -> int:
    if message_id is not None:
        try:
            await bot.edit_message_text(
                text, chat_id=chat_id, message_id=message_id, reply_markup=keyboard
            )
        except TelegramBadRequest as error:
            if NOT_MODIFIED in str(error):
                return message_id
            logger.info("message.text_edit_failed", message_id=message_id, reason=str(error))
        else:
            return message_id

    sent = await bot.send_message(chat_id, text, reply_markup=keyboard)
    return sent.message_id


def as_photo(image: bytes | str, filename: str) -> Photo:
    if isinstance(image, str):
        return image
    return BufferedInputFile(image, filename=filename)


def photo_file_id(message: Message) -> str | None:
    return message.photo[-1].file_id if message.photo else None


async def _send_card(
    bot: Bot,
    chat_id: int,
    photo: Photo,
    caption: str,
    keyboard: InlineKeyboardMarkup | None,
) -> Message:
    return await bot.send_photo(chat_id, photo, caption=caption, reply_markup=keyboard)


async def _delete_quietly(bot: Bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramBadRequest as error:
        logger.info("message.delete_failed", message_id=message_id, reason=str(error))
