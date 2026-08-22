from typing import Final

from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendPhoto

from fake_bot import CHAT_ID, HOST_ID, FakeSession, make_bot
from fake_words import WORD
from undercover.bot.role_delivery import deliver_roles, render_role_card
from undercover.game.models import GameMode, GameSessionState, GameStatus, PlayerState
from undercover.texts import Delivery

SESSION_ID: Final = "11111111-1111-1111-1111-111111111111"
HINT: Final = "её режут на куски"


def make_state(ids: tuple[int | None, ...] = (10, 20, 30)) -> GameSessionState:
    return GameSessionState(
        session_id=SESSION_ID,
        chat_id=CHAT_ID,
        host_user_id=HOST_ID,
        mode=GameMode.GROUP,
        status=GameStatus.SETUP,
        players=[
            PlayerState(order_index=index, name=f"Игрок-{index}", is_spy=index == 1, user_id=user)
            for index, user in enumerate(ids)
        ],
        word_id=42,
        word_text=WORD,
        hint_by_spy={1: HINT},
    )


async def test_every_player_gets_a_card_in_their_own_chat() -> None:
    session = FakeSession()

    undelivered = await deliver_roles(make_bot(session), make_state())

    assert undelivered == []
    assert {call.chat_id for call in session.calls(SendPhoto)} == {10, 20, 30}


async def test_the_card_arrives_with_a_caption() -> None:
    session = FakeSession()

    await deliver_roles(make_bot(session), make_state())

    assert {call.caption for call in session.calls(SendPhoto)} == {Delivery.ROLE_CAPTION}


async def test_a_blocked_player_comes_back_as_undelivered() -> None:
    session = FakeSession()
    session.failures[SendPhoto] = TelegramForbiddenError(
        method=SendPhoto(chat_id=10, photo="x"), message="bot was blocked by the user"
    )

    undelivered = await deliver_roles(make_bot(session), make_state(ids=(10,)))

    assert [player.name for player in undelivered] == ["Игрок-0"]


async def test_one_blocked_player_does_not_stop_the_others() -> None:
    session = FakeSession()
    session.failures[SendPhoto] = TelegramForbiddenError(
        method=SendPhoto(chat_id=10, photo="x"), message="bot was blocked by the user"
    )

    undelivered = await deliver_roles(make_bot(session), make_state())

    assert len(undelivered) == 1
    assert len(session.calls(SendPhoto)) == 3


async def test_a_player_without_a_telegram_id_is_undelivered_without_a_request() -> None:
    session = FakeSession()

    undelivered = await deliver_roles(make_bot(session), make_state(ids=(10, 20, None)))

    assert [player.name for player in undelivered] == ["Игрок-2"]
    assert len(session.calls(SendPhoto)) == 2


def test_the_spy_card_differs_from_the_civilian_one() -> None:
    state = make_state()

    assert render_role_card(state.players[1], state) != render_role_card(state.players[0], state)
