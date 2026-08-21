import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import DeleteMessage, EditMessageMedia, SendPhoto
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from fake_bot import (
    CHAT_ID,
    FIRST_MESSAGE_ID,
    SENT_MESSAGE_ID,
    FakeSession,
    make_bot,
    photo_message,
)
from undercover.bot.message_utils import photo_file_id, show_or_advance_card

CAPTION = "Ход 1 из 4"
KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[[InlineKeyboardButton(text="👁 Посмотреть", callback_data="reveal:show")]]
)


def photo() -> BufferedInputFile:
    return BufferedInputFile(b"png-bytes", filename="card.png")


@pytest.fixture
def session() -> FakeSession:
    return FakeSession()


async def test_first_card_is_sent_as_new_message(session: FakeSession) -> None:
    message = await show_or_advance_card(
        make_bot(session), CHAT_ID, None, photo(), CAPTION, KEYBOARD
    )

    (sent,) = session.calls(SendPhoto)
    assert (sent.chat_id, sent.caption, sent.reply_markup) == (CHAT_ID, CAPTION, KEYBOARD)
    assert message.message_id == SENT_MESSAGE_ID


async def test_next_card_edits_the_same_message(session: FakeSession) -> None:
    message = await show_or_advance_card(
        make_bot(session), CHAT_ID, FIRST_MESSAGE_ID, photo(), CAPTION, KEYBOARD
    )

    (edited,) = session.calls(EditMessageMedia)
    assert (edited.chat_id, edited.message_id) == (CHAT_ID, FIRST_MESSAGE_ID)
    assert edited.media.caption == CAPTION
    assert edited.reply_markup == KEYBOARD
    assert not session.calls(SendPhoto) and not session.calls(DeleteMessage)
    assert message.message_id == FIRST_MESSAGE_ID


async def test_rejected_edit_falls_back_to_delete_and_send(session: FakeSession) -> None:
    session.failures[EditMessageMedia] = TelegramBadRequest(
        method=DeleteMessage(chat_id=CHAT_ID, message_id=FIRST_MESSAGE_ID),
        message="message can't be edited",
    )

    message = await show_or_advance_card(
        make_bot(session), CHAT_ID, FIRST_MESSAGE_ID, photo(), CAPTION, KEYBOARD
    )

    (deleted,) = session.calls(DeleteMessage)
    (sent,) = session.calls(SendPhoto)
    assert deleted.message_id == FIRST_MESSAGE_ID
    assert sent.caption == CAPTION
    assert message.message_id != FIRST_MESSAGE_ID, "новое сообщение — новый message_id"


async def test_unexpected_true_from_edit_falls_back_too(session: FakeSession) -> None:
    session.results[EditMessageMedia] = [True]

    message = await show_or_advance_card(
        make_bot(session), CHAT_ID, FIRST_MESSAGE_ID, photo(), CAPTION, KEYBOARD
    )

    assert session.calls(DeleteMessage) and session.calls(SendPhoto)
    assert message.message_id != FIRST_MESSAGE_ID


async def test_undeletable_message_does_not_stop_the_game(session: FakeSession) -> None:
    session.failures[EditMessageMedia] = TelegramBadRequest(
        method=DeleteMessage(chat_id=CHAT_ID, message_id=FIRST_MESSAGE_ID),
        message="message to edit not found",
    )
    session.failures[DeleteMessage] = TelegramBadRequest(
        method=DeleteMessage(chat_id=CHAT_ID, message_id=FIRST_MESSAGE_ID),
        message="message to delete not found",
    )

    message = await show_or_advance_card(
        make_bot(session), CHAT_ID, FIRST_MESSAGE_ID, photo(), CAPTION, KEYBOARD
    )

    assert session.calls(SendPhoto)
    assert message.message_id != FIRST_MESSAGE_ID


async def test_cached_file_id_is_forwarded_as_is(session: FakeSession) -> None:
    await show_or_advance_card(make_bot(session), CHAT_ID, None, "AgACAgIAA", CAPTION)

    (sent,) = session.calls(SendPhoto)
    assert sent.photo == "AgACAgIAA"


def test_photo_file_id_takes_the_largest_variant() -> None:
    assert photo_file_id(photo_message(FIRST_MESSAGE_ID)) == f"photo-{FIRST_MESSAGE_ID}"
