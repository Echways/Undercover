import re
from dataclasses import dataclass
from typing import Any, Final

import pytest
from aiogram import Bot, Dispatcher, F, Router
from aiogram.methods import AnswerCallbackQuery, EditMessageMedia, SendPhoto
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, Message
from aiogram_dialog import DialogManager, StartMode, setup_dialogs
from aiogram_dialog.test_tools import BotClient, MockMessageManager
from aiogram_dialog.test_tools.keyboard import InlineButtonTextLocator
from aiogram_dialog.test_tools.memory_storage import JsonMemoryStorage

from fake_bot import CHAT_ID, HOST_ID, FakeSession, callback_update, make_bot
from fake_games import FakeGameStateRepository
from fake_words import WORD, FakeWords, pizza
from undercover.bot.routers.discussion import (
    FinalAction,
    FinalCB,
    TalkAction,
    TalkCB,
    create_discussion_router,
    start_discussion,
)
from undercover.bot.routers.reveal import create_reveal_router, start_reveal
from undercover.bot.routers.setup_dialog import Setup, create_setup_dialog
from undercover.game.models import GameSessionState, GameStatus, PlayerState
from undercover.texts import Buttons, Discussion, Errors
from undercover.texts import Setup as SetupTexts

SESSION_ID: Final = "11111111-1111-1111-1111-111111111111"
NAMES: Final = ("Аня", "Борис", "Вера", "Галя")
SPY_INDEX: Final = 1
HINT: Final = "её режут на куски"
OUTSIDER_ID: Final = HOST_ID + 1


def make_state(
    names: tuple[str, ...] = NAMES,
    spies: tuple[int, ...] = (SPY_INDEX,),
    **overrides: object,
) -> GameSessionState:
    defaults: dict[str, object] = {
        "session_id": SESSION_ID,
        "chat_id": CHAT_ID,
        "host_user_id": HOST_ID,
        "status": GameStatus.DISCUSSION,
        "players": [
            PlayerState(order_index=index, name=name, is_spy=index in spies, has_viewed=True)
            for index, name in enumerate(names)
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

    async def __call__(self, state: GameSessionState) -> None:
        self.states.append(state.model_copy(deep=True))
        if self.failure is not None:
            raise self.failure


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
async def table(words: FakeWords, log: RecordingLog) -> Table:
    session = FakeSession()
    bot = make_bot(session)
    games = FakeGameStateRepository()
    dispatcher = Dispatcher(storage=JsonMemoryStorage(), games=games)
    dispatcher.include_router(start_router())
    dispatcher.include_router(create_setup_dialog(words.open, start_reveal))
    dispatcher.include_router(create_reveal_router(start_discussion))
    dispatcher.include_router(create_discussion_router(words.open, log))
    messages = MockMessageManager()
    setup_dialogs(dispatcher, message_manager=messages)

    return Table(
        client=BotClient(dispatcher, user_id=HOST_ID, chat_id=CHAT_ID, chat_type="group", bot=bot),
        dispatcher=dispatcher,
        bot=bot,
        session=session,
        messages=messages,
        games=games,
        words=words,
        log=log,
    )


async def talking(table: Table, **overrides: Any) -> GameSessionState:
    state = make_state(**overrides)
    await table.games.save(state)
    await start_discussion(table.bot, table.games, state)
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


async def test_the_whole_game_from_setup_to_the_final_screen(table: Table) -> None:
    await table.send("/start")
    await table.send("2")
    await table.send("1")
    await table.send("Аня")
    await table.send("Борис")
    await table.click(Buttons.PLAY)

    dealt = table.games.stored
    assert [player.name for player in dealt.players] == ["Аня", "Борис"]
    assert dealt.status is GameStatus.REVEAL

    await table.press(Buttons.SHOW_CARD)
    await table.press(Buttons.NEXT_PLAYER)
    await table.press(Buttons.SHOW_CARD)
    await table.press(Buttons.START_DISCUSSION)

    talk = table.games.stored
    assert talk.status is GameStatus.DISCUSSION
    assert sorted(talk.discussion_order) == [0, 1], "высказываются все и по разу"
    assert talk.discussion_cursor == 0
    opening = table.card

    assert opening.texts == (Buttons.NEXT_SPEAKER, Buttons.SHOW_SPIES)

    await table.press(Buttons.NEXT_SPEAKER)

    assert table.games.stored.discussion_cursor == 1
    assert table.card.texts == (
        Buttons.ANOTHER_ROUND,
        Buttons.SHOW_SPIES,
    ), "все высказались — остаётся пойти на второй круг или искать шпиона"

    await table.press(Buttons.SHOW_SPIES)

    spy = next(player.name for player in talk.players if player.is_spy)
    final = table.card

    assert final.caption == Discussion.FINAL_CAPTION.format(
        title=Discussion.SPY_TITLE_ONE, spies=spy, word=WORD
    )
    assert final.texts == (Buttons.PLAY_AGAIN, Buttons.NEW_GAME)
    assert table.games.stored.status is GameStatus.FINISHED
    assert table.alerts == [None] * 6, "ни одно нажатие не отклонено"
    assert len(table.session.calls(SendPhoto)) == 1, "вся партия прожила в одном сообщении"

    (recorded,) = table.log.states
    assert (recorded.chat_id, recorded.host_user_id) == (CHAT_ID, HOST_ID)
    assert (len(recorded.players), recorded.word_id) == (2, pizza().id)


async def test_discussion_order_is_a_permutation_of_the_roster(table: Table) -> None:
    state = await talking(table)

    assert sorted(state.discussion_order) == list(range(len(NAMES)))
    assert state.discussion_cursor == 0


async def test_every_player_speaks_once_and_then_the_hunt_begins(table: Table) -> None:
    state = await talking(table)

    for cursor in range(len(NAMES) - 1):
        speaker = NAMES[state.discussion_order[cursor]]
        assert table.card.caption == Discussion.TALK_CAPTION.format(
            position=cursor + 1, total=len(NAMES), name=speaker
        )
        assert table.card.texts == (Buttons.NEXT_SPEAKER, Buttons.SHOW_SPIES)
        await table.press(Buttons.NEXT_SPEAKER)

    last = NAMES[state.discussion_order[-1]]
    assert table.card.caption == Discussion.LAST_TALK_CAPTION.format(name=last)
    assert table.card.texts == (Buttons.ANOTHER_ROUND, Buttons.SHOW_SPIES)
    assert sorted(spoken_names(table)) == sorted(NAMES)


async def test_a_stale_button_does_not_skip_a_speaker(table: Table) -> None:
    await talking(table)
    stale = table.card.callback_data(Buttons.NEXT_SPEAKER)
    await table.press(Buttons.NEXT_SPEAKER)
    shown = len(table.cards)

    await table.tap(stale)

    assert table.alerts[-1] == Errors.STALE_TURN
    assert table.games.stored.discussion_cursor == 1
    assert len(table.cards) == shown


async def test_an_outsider_does_not_move_the_discussion(table: Table) -> None:
    await talking(table)

    await table.press(Buttons.NEXT_SPEAKER, user_id=OUTSIDER_ID)

    assert table.alerts[-1] == Errors.NOT_HOST
    assert table.games.stored.discussion_cursor == 0


async def test_there_is_no_speaker_after_the_last_one(table: Table) -> None:
    state = await talking(table)
    last = len(NAMES) - 1

    await table.tap(
        TalkCB(action=TalkAction.NEXT, session_id=SESSION_ID, cursor=state.discussion_cursor).pack()
    )
    for _ in range(1, last):
        await table.press(Buttons.NEXT_SPEAKER)

    await table.tap(TalkCB(action=TalkAction.NEXT, session_id=SESSION_ID, cursor=last).pack())

    assert table.alerts[-1] == Discussion.ALL_SPOKE
    assert table.games.stored.discussion_cursor == last


async def test_a_broken_speaking_order_is_reported(table: Table) -> None:
    await table.games.save(make_state(discussion_order=[0, 99, 1], discussion_cursor=0))

    await table.tap(TalkCB(action=TalkAction.NEXT, session_id=SESSION_ID, cursor=0).pack())

    assert table.alerts == [Errors.BROKEN_SESSION]
    assert not table.cards


async def test_another_round_waits_until_everyone_has_spoken(table: Table) -> None:
    state = await talking(table)

    for _ in range(len(state.discussion_order) - 1):
        assert Buttons.ANOTHER_ROUND not in table.card.texts
        await table.press(Buttons.NEXT_SPEAKER)

    assert table.card.texts == (Buttons.ANOTHER_ROUND, Buttons.SHOW_SPIES)


async def test_another_round_starts_the_circle_over_in_the_same_order(table: Table) -> None:
    state = await all_spoken(table)

    await table.press(Buttons.ANOTHER_ROUND)

    repeated = table.games.stored
    assert repeated.discussion_order == state.discussion_order
    assert repeated.discussion_cursor == 0
    assert repeated.discussion_round == 2
    assert repeated.status is GameStatus.DISCUSSION


async def test_the_first_round_caption_stays_free_of_numbering(table: Table) -> None:
    state = await talking(table)

    assert state.discussion_round == 1
    assert table.card.caption == Discussion.TALK_CAPTION.format(
        position=1, total=len(NAMES), name=NAMES[state.discussion_order[0]]
    )


async def test_a_later_round_is_numbered_in_the_caption(table: Table) -> None:
    state = await all_spoken(table)

    await table.press(Buttons.ANOTHER_ROUND)

    assert table.card.caption == Discussion.ROUND_PREFIX.format(
        round=2
    ) + Discussion.TALK_CAPTION.format(
        position=1, total=len(NAMES), name=NAMES[state.discussion_order[0]]
    )


async def test_a_later_round_numbers_its_last_speaker_too(table: Table) -> None:
    state = await all_spoken(table)

    await table.press(Buttons.ANOTHER_ROUND)
    for _ in range(len(NAMES) - 1):
        await table.press(Buttons.NEXT_SPEAKER)

    assert table.card.caption == Discussion.ROUND_PREFIX.format(
        round=2
    ) + Discussion.LAST_TALK_CAPTION.format(name=NAMES[state.discussion_order[-1]])


async def test_another_round_does_not_cut_the_current_one_short(table: Table) -> None:
    await talking(table)

    await table.tap(TalkCB(action=TalkAction.ROUND, session_id=SESSION_ID, cursor=0).pack())

    assert table.alerts[-1] == Errors.STALE_TURN
    assert table.games.stored.discussion_round == 1
    assert table.games.stored.discussion_cursor == 0


async def test_a_broken_order_does_not_open_another_round(table: Table) -> None:
    await table.games.save(
        make_state(names=("Аня", "Борис"), discussion_order=[99, 0], discussion_cursor=1)
    )

    await table.tap(TalkCB(action=TalkAction.ROUND, session_id=SESSION_ID, cursor=1).pack())

    assert table.alerts == [Errors.BROKEN_SESSION]
    assert not table.cards
    assert table.games.stored.discussion_round == 1


async def test_a_stale_another_round_button_does_not_restart_the_circle(table: Table) -> None:
    await all_spoken(table)
    stale = table.card.callback_data(Buttons.ANOTHER_ROUND)
    await table.press(Buttons.ANOTHER_ROUND)
    shown = len(table.cards)

    await table.tap(stale)

    assert table.alerts[-1] == Errors.STALE_TURN
    assert table.games.stored.discussion_round == 2
    assert len(table.cards) == shown


async def test_an_outsider_does_not_start_another_round(table: Table) -> None:
    await all_spoken(table)

    await table.press(Buttons.ANOTHER_ROUND, user_id=OUTSIDER_ID)

    assert table.alerts[-1] == Errors.NOT_HOST
    assert table.games.stored.discussion_round == 1


async def test_the_hunt_still_ends_the_game_after_another_round(table: Table) -> None:
    await all_spoken(table)
    await table.press(Buttons.ANOTHER_ROUND)

    await table.press(Buttons.SHOW_SPIES)

    assert table.games.stored.status is GameStatus.FINISHED


async def test_the_next_game_counts_rounds_from_the_first(table: Table) -> None:
    await all_spoken(table)
    await table.press(Buttons.ANOTHER_ROUND)
    await table.press(Buttons.SHOW_SPIES)

    await table.press(Buttons.PLAY_AGAIN)

    assert table.games.stored.discussion_round == 1


async def test_the_final_screen_names_every_spy_and_the_word(table: Table) -> None:
    await talking(table, names=("Аня", "Борис", "Вера", "Галя", "Дима", "Егор"), spies=(1, 4))

    await table.press(Buttons.SHOW_SPIES)

    assert table.card.caption == Discussion.FINAL_CAPTION.format(
        title=Discussion.SPY_TITLE_MANY, spies="Борис, Дима", word=WORD
    )


async def test_the_finished_game_waits_for_the_next_decision(table: Table) -> None:
    state = await finished(table)

    assert state.status is GameStatus.FINISHED
    assert await table.games.load(SESSION_ID) is not None


async def test_the_finished_game_goes_to_the_journal(table: Table) -> None:
    state = await finished(table, spies=(1, 2))

    (recorded,) = table.log.states
    assert recorded.session_id == state.session_id
    assert recorded.status is GameStatus.FINISHED
    assert [player.is_spy for player in recorded.players] == [False, True, True, False]


async def test_a_broken_journal_does_not_break_the_final_screen(table: Table) -> None:
    table.log.failure = RuntimeError("нет связи с базой")

    await talking(table)
    await table.press(Buttons.SHOW_SPIES)

    assert table.card.texts == (Buttons.PLAY_AGAIN, Buttons.NEW_GAME)
    assert table.games.stored.status is GameStatus.FINISHED
    assert table.alerts[-1] is None


async def test_discussion_buttons_are_dead_after_the_game_is_over(table: Table) -> None:
    await talking(table)
    stale = table.card.callback_data(Buttons.NEXT_SPEAKER)
    await table.press(Buttons.SHOW_SPIES)

    await table.tap(stale)

    assert table.alerts[-1] == Discussion.WRONG_PHASE


async def test_final_buttons_are_dead_while_the_game_is_on(table: Table) -> None:
    await talking(table)

    await table.tap(FinalCB(action=FinalAction.AGAIN, session_id=SESSION_ID).pack())

    assert table.alerts[-1] == Discussion.GAME_IS_ON
    assert table.games.stored.status is GameStatus.DISCUSSION


async def test_an_unknown_session_is_reported(table: Table) -> None:
    await table.tap(FinalCB(action=FinalAction.AGAIN, session_id="нет-такой").pack())

    assert table.alerts == [Errors.SESSION_NOT_FOUND]
    assert not table.cards


async def test_play_again_keeps_the_roster_and_deals_a_fresh_game(table: Table) -> None:
    old = await finished(table)

    await table.press(Buttons.PLAY_AGAIN)

    fresh = table.games.stored
    assert fresh.session_id != old.session_id, "это новая партия, а не продолжение старой"
    assert [player.name for player in fresh.players] == list(NAMES)
    assert [player.order_index for player in fresh.players] == list(range(len(NAMES)))
    assert sum(player.is_spy for player in fresh.players) == 1
    assert not any(player.has_viewed for player in fresh.players)
    assert fresh.status is GameStatus.REVEAL
    assert fresh.reveal_cursor == 0
    assert fresh.discussion_order == []


async def test_play_again_keeps_the_chosen_categories(table: Table) -> None:
    await finished(table, category_ids=[2, 5])

    await table.press(Buttons.PLAY_AGAIN)

    assert table.games.stored.category_ids == [2, 5]
    assert table.words.asked_categories[-1] in (2, 5)


async def test_play_again_without_words_in_the_chosen_categories_is_explained(
    table: Table,
) -> None:
    old = await finished(table, category_ids=[2])
    table.words.empty_categories = frozenset({2})

    await table.press(Buttons.PLAY_AGAIN)

    assert table.alerts[-1] == Errors.EMPTY_CATEGORIES
    assert table.games.stored.session_id == old.session_id


async def test_play_again_forgets_the_finished_game(table: Table) -> None:
    old = await finished(table)

    await table.press(Buttons.PLAY_AGAIN)

    active = await table.games.load_active(CHAT_ID)

    assert await table.games.load(old.session_id) is None
    assert active is not None
    assert active.session_id == table.games.stored.session_id


async def test_play_again_reuses_the_cached_hidden_cards(table: Table) -> None:
    await talking(table)
    cached = table.games.stored
    for player in cached.players:
        player.card_file_id = f"cached-{player.order_index}"
    await table.games.save(cached)
    await table.press(Buttons.SHOW_SPIES)

    await table.press(Buttons.PLAY_AGAIN)

    assert table.card.photo == "cached-0"
    assert [player.card_file_id for player in table.games.stored.players] == [
        f"cached-{index}" for index in range(len(NAMES))
    ]


async def test_play_again_continues_in_the_same_message(table: Table) -> None:
    await finished(table)
    sent = len(table.session.calls(SendPhoto))

    await table.press(Buttons.PLAY_AGAIN)

    assert len(table.session.calls(SendPhoto)) == sent, "экран партии остался тем же сообщением"


async def test_play_again_without_a_word_keeps_the_finished_game(table: Table) -> None:
    old = await finished(table)
    table.words.word = None

    await table.press(Buttons.PLAY_AGAIN)

    assert table.alerts[-1] == Errors.EMPTY_CATALOG
    assert table.games.stored.session_id == old.session_id

    table.words.word = pizza()
    await table.press(Buttons.PLAY_AGAIN)

    assert table.games.stored.session_id != old.session_id


async def test_new_game_wipes_the_session_and_opens_the_setup(table: Table) -> None:
    old = await finished(table)

    await table.press(Buttons.NEW_GAME)

    assert await table.games.load(old.session_id) is None
    assert SetupTexts.ASK_PLAYERS_COUNT in (table.window.text or "")


async def test_new_game_asks_for_the_roster_from_scratch(table: Table) -> None:
    await finished(table)
    await table.press(Buttons.NEW_GAME)

    await table.send("2")
    await table.send("1")
    await table.send("Зина")
    await table.send("Игорь")
    await table.click(Buttons.PLAY)

    assert [player.name for player in table.games.stored.players] == ["Зина", "Игорь"]
