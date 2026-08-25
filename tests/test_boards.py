from typing import Final

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageCaption, EditMessageMedia, SendPhoto
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from fake_bot import CHAT_ID, FIRST_MESSAGE_ID, HOST_ID, FakeSession, make_bot
from undercover.bot.boards import FeedBoard, PhaseBoard, SingleCardBoard, board_for
from undercover.game.models import GameSessionState, GameStatus, PlayerState, Seating

SESSION_ID: Final = "11111111-1111-1111-1111-111111111111"
KEYBOARD: Final = InlineKeyboardMarkup(
    inline_keyboard=[[InlineKeyboardButton(text="Следующий игрок", callback_data="talk:next")]]
)


def make_state(seating: Seating, message_id: int | None = FIRST_MESSAGE_ID) -> GameSessionState:
    return GameSessionState(
        session_id=SESSION_ID,
        chat_id=CHAT_ID,
        host_user_id=HOST_ID,
        seating=seating,
        status=GameStatus.DISCUSSION,
        players=[PlayerState(order_index=0, name="Аня", is_spy=True)],
        word_id=1,
        word_text="пицца",
        current_message_id=message_id,
    )


def test_board_is_chosen_by_the_mode_of_the_session() -> None:
    assert isinstance(board_for(make_state(Seating.HOT_SEAT)), SingleCardBoard)
    assert isinstance(board_for(make_state(Seating.GROUP)), FeedBoard)


async def test_hot_seat_keeps_the_whole_game_in_one_message() -> None:
    session = FakeSession()

    message_id = await SingleCardBoard().show(
        make_bot(session), make_state(Seating.HOT_SEAT), "photo-id", "Говорит: Аня", KEYBOARD
    )

    assert session.calls(EditMessageMedia)
    assert not session.calls(SendPhoto)
    assert message_id == FIRST_MESSAGE_ID


async def test_hot_seat_freezes_nothing_because_nothing_scrolls_away() -> None:
    session = FakeSession()

    await SingleCardBoard().revise(make_bot(session), make_state(Seating.HOT_SEAT), "Говорит: Аня")

    assert session.requests == []


async def test_the_group_gets_a_fresh_message_for_every_speaker() -> None:
    session = FakeSession()

    message_id = await FeedBoard().show(
        make_bot(session), make_state(Seating.GROUP), "photo-id", "Говорит: Аня", KEYBOARD
    )

    assert session.calls(SendPhoto)
    assert not session.calls(EditMessageMedia)
    assert message_id != FIRST_MESSAGE_ID


async def test_the_finished_turn_loses_its_buttons_and_keeps_a_report() -> None:
    session = FakeSession()

    await FeedBoard().revise(
        make_bot(session), make_state(Seating.GROUP), "Говорит: Аня\nВремя вышло"
    )

    (frozen,) = session.calls(EditMessageCaption)
    assert frozen.message_id == FIRST_MESSAGE_ID
    assert frozen.caption == "Говорит: Аня\nВремя вышло"
    assert frozen.reply_markup is None


async def test_the_first_turn_of_a_group_game_has_nothing_to_freeze() -> None:
    session = FakeSession()

    await FeedBoard().revise(
        make_bot(session), make_state(Seating.GROUP, message_id=None), "Говорит: Аня"
    )

    assert session.requests == []


async def test_a_deleted_turn_message_does_not_break_the_game() -> None:
    session = FakeSession()
    session.failures[EditMessageCaption] = TelegramBadRequest(
        method=EditMessageCaption(caption="x"), message="message to edit not found"
    )

    await FeedBoard().revise(make_bot(session), make_state(Seating.GROUP), "Говорит: Аня")


async def test_a_frozen_turn_can_keep_its_buttons_when_the_round_is_over() -> None:
    session = FakeSession()

    await FeedBoard().revise(make_bot(session), make_state(Seating.GROUP), "Говорит: Аня", KEYBOARD)

    (frozen,) = session.calls(EditMessageCaption)
    assert frozen.reply_markup == KEYBOARD


async def test_a_live_screen_can_be_repainted_with_new_buttons() -> None:
    session = FakeSession()

    await FeedBoard().revise(
        make_bot(session), make_state(Seating.GROUP), "Проголосовали 2 из 4", KEYBOARD
    )

    (repainted,) = session.calls(EditMessageCaption)
    assert repainted.caption == "Проголосовали 2 из 4"
    assert repainted.reply_markup == KEYBOARD


def test_both_boards_satisfy_the_phase_protocol() -> None:
    boards: tuple[PhaseBoard, ...] = (SingleCardBoard(), FeedBoard())

    assert len(boards) == 2
