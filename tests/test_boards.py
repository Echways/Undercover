from typing import Final

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageCaption, EditMessageMedia, SendPhoto
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from fake_bot import CHAT_ID, FIRST_MESSAGE_ID, HOST_ID, FakeSession, make_bot
from undercover.bot.boards import FeedBoard, SingleCardBoard, board_for
from undercover.game.models import GameMode, GameSessionState, GameStatus, PlayerState

SESSION_ID: Final = "11111111-1111-1111-1111-111111111111"
KEYBOARD: Final = InlineKeyboardMarkup(
    inline_keyboard=[[InlineKeyboardButton(text="Следующий игрок", callback_data="talk:next")]]
)


def make_state(mode: GameMode, message_id: int | None = FIRST_MESSAGE_ID) -> GameSessionState:
    return GameSessionState(
        session_id=SESSION_ID,
        chat_id=CHAT_ID,
        host_user_id=HOST_ID,
        mode=mode,
        status=GameStatus.DISCUSSION,
        players=[PlayerState(order_index=0, name="Аня", is_spy=True)],
        word_id=1,
        word_text="пицца",
        current_message_id=message_id,
    )


def test_board_is_chosen_by_the_mode_of_the_session() -> None:
    assert isinstance(board_for(make_state(GameMode.HOT_SEAT)), SingleCardBoard)
    assert isinstance(board_for(make_state(GameMode.GROUP)), FeedBoard)


async def test_hot_seat_keeps_the_whole_game_in_one_message() -> None:
    session = FakeSession()

    message_id = await SingleCardBoard().open_turn(
        make_bot(session), make_state(GameMode.HOT_SEAT), "photo-id", "Говорит: Аня", KEYBOARD
    )

    assert session.calls(EditMessageMedia)
    assert not session.calls(SendPhoto)
    assert message_id == FIRST_MESSAGE_ID


async def test_hot_seat_freezes_nothing_because_nothing_scrolls_away() -> None:
    session = FakeSession()

    await SingleCardBoard().close_turn(
        make_bot(session), make_state(GameMode.HOT_SEAT), "Говорит: Аня"
    )

    assert session.requests == []


async def test_the_group_gets_a_fresh_message_for_every_speaker() -> None:
    session = FakeSession()

    message_id = await FeedBoard().open_turn(
        make_bot(session), make_state(GameMode.GROUP), "photo-id", "Говорит: Аня", KEYBOARD
    )

    assert session.calls(SendPhoto)
    assert not session.calls(EditMessageMedia)
    assert message_id != FIRST_MESSAGE_ID


async def test_the_finished_turn_loses_its_buttons_and_keeps_a_report() -> None:
    session = FakeSession()

    await FeedBoard().close_turn(
        make_bot(session), make_state(GameMode.GROUP), "Говорит: Аня\nВремя вышло"
    )

    (frozen,) = session.calls(EditMessageCaption)
    assert frozen.message_id == FIRST_MESSAGE_ID
    assert frozen.caption == "Говорит: Аня\nВремя вышло"
    assert frozen.reply_markup is None


async def test_the_first_turn_of_a_group_game_has_nothing_to_freeze() -> None:
    session = FakeSession()

    await FeedBoard().close_turn(
        make_bot(session), make_state(GameMode.GROUP, message_id=None), "Говорит: Аня"
    )

    assert session.requests == []


async def test_a_deleted_turn_message_does_not_break_the_game() -> None:
    session = FakeSession()
    session.failures[EditMessageCaption] = TelegramBadRequest(
        method=EditMessageCaption(caption="x"), message="message to edit not found"
    )

    await FeedBoard().close_turn(make_bot(session), make_state(GameMode.GROUP), "Говорит: Аня")
