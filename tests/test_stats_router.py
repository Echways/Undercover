from typing import Final

import pytest
from aiogram import Dispatcher
from aiogram.enums import ChatType
from aiogram.methods import AnswerCallbackQuery, SendMessage

from fake_bot import CHAT_ID, HOST_ID, FakeSession, callback_update, make_bot, message_update
from fake_stats import FakeStats
from undercover.bot.callbacks import StatsAction, StatsCB
from undercover.bot.routers.stats import create_stats_router
from undercover.game.stats import Champion, ChatTotals, HallOfFame, PlayerProfile
from undercover.texts import STATS_COMMAND, Buttons, Stats

COMMAND: Final = f"/{STATS_COMMAND}"
HALL: Final = HallOfFame(
    totals=ChatTotals(games=9, civilian_wins=5, spy_wins=3),
    first_victim=Champion(name="Вера", value=4),
)
PROFILE: Final = PlayerProfile(games=4, wins=3, spy_games=1, spy_wins=1, streak=2, first_outs=0)


@pytest.fixture
def stats() -> FakeStats:
    return FakeStats(hall=HALL, profile=PROFILE)


@pytest.fixture
def table(stats: FakeStats) -> tuple[Dispatcher, FakeSession]:
    session = FakeSession()
    dispatcher = Dispatcher()
    dispatcher.include_router(create_stats_router(stats.open))
    return dispatcher, session


async def test_the_command_paints_the_hall_in_a_group(
    table: tuple[Dispatcher, FakeSession],
) -> None:
    dispatcher, session = table

    await dispatcher.feed_update(make_bot(session), message_update(COMMAND))

    (sent,) = session.calls(SendMessage)
    assert "Первая жертва: Вера — 4 раза" in (sent.text or "")


async def test_the_hall_carries_the_private_card_button(
    table: tuple[Dispatcher, FakeSession],
) -> None:
    dispatcher, session = table

    await dispatcher.feed_update(make_bot(session), message_update(COMMAND))

    (sent,) = session.calls(SendMessage)
    assert sent.reply_markup is not None
    assert sent.reply_markup.inline_keyboard[0][0].text == Buttons.MY_STATS


async def test_the_command_in_a_private_chat_explains_itself(
    table: tuple[Dispatcher, FakeSession],
) -> None:
    dispatcher, session = table

    await dispatcher.feed_update(
        make_bot(session), message_update(COMMAND, chat_type=ChatType.PRIVATE)
    )

    (sent,) = session.calls(SendMessage)
    assert Stats.PRIVATE in (sent.text or "")


async def test_the_lobby_button_opens_the_hall(
    table: tuple[Dispatcher, FakeSession],
) -> None:
    dispatcher, session = table

    await dispatcher.feed_update(
        make_bot(session), callback_update(StatsCB(action=StatsAction.BOARD).pack())
    )

    assert len(session.calls(SendMessage)) == 1
    assert session.calls(AnswerCallbackQuery)[0].text is None


async def test_the_private_card_arrives_as_an_alert(
    table: tuple[Dispatcher, FakeSession], stats: FakeStats
) -> None:
    dispatcher, session = table

    await dispatcher.feed_update(
        make_bot(session), callback_update(StatsCB(action=StatsAction.ME).pack())
    )

    (answered,) = session.calls(AnswerCallbackQuery)
    assert answered.show_alert
    assert "Партий: 4 · Побед: 3 (75%)" in (answered.text or "")
    assert stats.asked == [(CHAT_ID, HOST_ID)]
    assert session.calls(SendMessage) == []


async def test_a_newcomer_gets_the_newcomer_alert(
    table: tuple[Dispatcher, FakeSession], stats: FakeStats
) -> None:
    stats.profile = None
    dispatcher, session = table

    await dispatcher.feed_update(
        make_bot(session), callback_update(StatsCB(action=StatsAction.ME).pack())
    )

    (answered,) = session.calls(AnswerCallbackQuery)
    assert answered.text == Stats.NO_PROFILE
