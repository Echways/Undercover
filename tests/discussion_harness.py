import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from functools import partial
from typing import Any, Final

import pytest
from aiogram import Bot, Dispatcher, F, Router
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageCaption,
    EditMessageMedia,
    SendPhoto,
)
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, Message
from aiogram_dialog import DialogManager, StartMode, setup_dialogs
from aiogram_dialog.test_tools import BotClient, MockMessageManager
from aiogram_dialog.test_tools.keyboard import InlineButtonTextLocator
from aiogram_dialog.test_tools.memory_storage import JsonMemoryStorage

from fake_bot import CHAT_ID, HOST_ID, FakeSession, callback_update, make_bot
from fake_games import FakeGameStateRepository
from fake_words import WORD, FakeWords, pizza
from undercover.bot.routers.discussion import create_discussion_router, start_discussion
from undercover.bot.routers.finale import create_finale_router
from undercover.bot.routers.reveal import create_reveal_router, start_reveal
from undercover.bot.routers.setup_dialog import create_setup_dialog
from undercover.bot.routers.setup_draft import Setup
from undercover.bot.routers.voting import create_voting_router, start_voting
from undercover.bot.turn_clock import KeyedLocks, TurnClock, TurnKeeper
from undercover.game.models import GameMode, GameSessionState, GameStatus, PlayerState
from undercover.texts import Buttons

SESSION_ID: Final = "11111111-1111-1111-1111-111111111111"
IDLE_TICK: Final = timedelta(minutes=1)
NAMES: Final = ("Аня", "Борис", "Вера", "Галя")
SPY_INDEX: Final = 1
HINT: Final = "её режут на куски"
OUTSIDER_ID: Final = HOST_ID + 1


def make_state(
    names: tuple[str, ...] = NAMES,
    spies: tuple[int, ...] = (SPY_INDEX,),
    ids: tuple[int, ...] | None = None,
    **overrides: object,
) -> GameSessionState:
    telegram_ids = ids or (None,) * len(names)
    defaults: dict[str, object] = {
        "session_id": SESSION_ID,
        "chat_id": CHAT_ID,
        "host_user_id": HOST_ID,
        "status": GameStatus.DISCUSSION,
        "players": [
            PlayerState(
                order_index=index,
                name=name,
                is_spy=index in spies,
                has_viewed=True,
                user_id=user_id,
            )
            for index, (name, user_id) in enumerate(zip(names, telegram_ids, strict=True))
        ],
        "word_id": 42,
        "word_text": WORD,
        "hint_by_spy": dict.fromkeys(spies, HINT),
        "reveal_cursor": len(names),
    }
    return GameSessionState.model_validate(defaults | overrides)


class RecordingLog:
    def __init__(self, failure: Exception | None = None) -> None:
        self.states: list[GameSessionState] = []
        self.failure = failure

    async def __call__(self, state: GameSessionState) -> int:
        self.states.append(state.model_copy(deep=True))
        if self.failure is not None:
            raise self.failure
        return len(self.states)


@dataclass(frozen=True, slots=True)
class Card:
    photo: bytes | str
    caption: str
    buttons: tuple[tuple[str, str], ...]

    @property
    def texts(self) -> tuple[str, ...]:
        return tuple(text for text, _ in self.buttons)

    def callback_data(self, button_text: str) -> str:
        found = dict(self.buttons).get(button_text)
        assert found is not None, f"на экране нет кнопки «{button_text}»: {self.texts}"
        return found


def cards(session: FakeSession) -> list[Card]:
    result: list[Card] = []
    for request in session.requests:
        if isinstance(request, SendPhoto):
            photo, caption, markup = request.photo, request.caption, request.reply_markup
        elif isinstance(request, EditMessageMedia):
            photo, caption, markup = (
                request.media.media,
                request.media.caption,
                request.reply_markup,
            )
        else:
            continue

        assert isinstance(markup, InlineKeyboardMarkup), "экран партии без кнопок — тупик"
        assert isinstance(photo, BufferedInputFile | str)
        result.append(
            Card(
                photo=photo.data if isinstance(photo, BufferedInputFile) else photo,
                caption=caption or "",
                buttons=tuple(
                    (button.text, button.callback_data)
                    for row in markup.inline_keyboard
                    for button in row
                    if button.callback_data is not None
                ),
            )
        )
    return result


@dataclass(frozen=True, slots=True)
class Table:
    client: BotClient
    dispatcher: Dispatcher
    bot: Bot
    session: FakeSession
    messages: MockMessageManager
    games: FakeGameStateRepository
    words: FakeWords
    log: RecordingLog
    keeper: TurnKeeper

    async def send(self, text: str) -> None:
        await self.client.send(text)

    async def click(self, button_text: str) -> None:
        await self.client.click(self.window, InlineButtonTextLocator(re.escape(button_text)))

    @property
    def window(self) -> Message:
        return self.messages.last_message()

    @property
    def card(self) -> Card:
        return cards(self.session)[-1]

    @property
    def cards(self) -> list[Card]:
        return cards(self.session)

    async def press(self, button_text: str, *, user_id: int = HOST_ID) -> None:
        await self.tap(self.card.callback_data(button_text), user_id=user_id)

    async def tap(self, callback_data: str, *, user_id: int = HOST_ID) -> None:
        await self.dispatcher.feed_update(self.bot, callback_update(callback_data, user_id=user_id))

    @property
    def alerts(self) -> list[str | None]:
        return [answer.text for answer in self.session.calls(AnswerCallbackQuery)]


def start_router() -> Router:
    router = Router(name="start")

    @router.message(F.text == "/start")
    async def open_setup(message: Message, dialog_manager: DialogManager) -> None:
        await dialog_manager.start(Setup.ask_players_count, mode=StartMode.RESET_STACK)

    return router


@pytest.fixture
def words() -> FakeWords:
    return FakeWords(pizza())


@pytest.fixture
def log() -> RecordingLog:
    return RecordingLog()


@pytest.fixture
async def table(words: FakeWords, log: RecordingLog) -> AsyncIterator[Table]:
    session = FakeSession()
    bot = make_bot(session)
    games = FakeGameStateRepository()
    keeper = TurnKeeper(clock=TurnClock(tick=IDLE_TICK), locks=KeyedLocks())
    begin_discussion = partial(start_discussion, keeper=keeper)
    begin_voting = partial(start_voting, keeper=keeper)
    dispatcher = Dispatcher(storage=JsonMemoryStorage(), games=games)
    dispatcher.include_router(start_router())
    dispatcher.include_router(create_setup_dialog(words.cached(), start_reveal))
    dispatcher.include_router(create_reveal_router(begin_discussion))
    dispatcher.include_router(create_discussion_router(keeper, begin_voting))
    dispatcher.include_router(create_voting_router(keeper, begin_discussion, log))
    dispatcher.include_router(create_finale_router(words.open, log, keeper, begin_discussion))
    messages = MockMessageManager()
    setup_dialogs(dispatcher, message_manager=messages)

    yield Table(
        client=BotClient(dispatcher, user_id=HOST_ID, chat_id=CHAT_ID, chat_type="group", bot=bot),
        dispatcher=dispatcher,
        bot=bot,
        session=session,
        messages=messages,
        games=games,
        words=words,
        log=log,
        keeper=keeper,
    )

    await keeper.clock.shutdown()


async def talking(table: Table, **overrides: Any) -> GameSessionState:
    state = make_state(**overrides)
    await table.games.save(state)
    await start_discussion(table.bot, table.games, state, table.keeper)
    return table.games.stored


async def finished(table: Table, **overrides: Any) -> GameSessionState:
    await talking(table, **overrides)
    await table.press(Buttons.SHOW_SPIES)
    return table.games.stored


async def all_spoken(table: Table, **overrides: Any) -> GameSessionState:
    state = await talking(table, **overrides)
    for _ in range(len(state.discussion_order) - 1):
        await table.press(Buttons.NEXT_SPEAKER)
    return table.games.stored


def spoken_names(table: Table) -> list[str]:
    return [name for card in table.cards for name in NAMES if name in card.caption]


async def voting(table: Table, **overrides: Any) -> GameSessionState:
    state = make_state(**overrides)
    await table.games.save(state)
    await start_voting(table.bot, table.games, state, table.keeper)
    return table.games.stored


async def group_voting(table: Table, ids: tuple[int, ...], **overrides: Any) -> GameSessionState:
    return await voting(table, ids=ids, mode=GameMode.GROUP, **overrides)


def repainted(table: Table) -> EditMessageCaption:
    edits = table.session.calls(EditMessageCaption)
    assert edits, "экран ни разу не перерисовывался"
    last = edits[-1]
    assert isinstance(last, EditMessageCaption)
    return last


def repainted_texts(table: Table) -> set[str]:
    markup = repainted(table).reply_markup
    assert isinstance(markup, InlineKeyboardMarkup)
    return {button.text for row in markup.inline_keyboard for button in row}
