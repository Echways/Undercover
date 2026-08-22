import inspect
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import pytest
from aiogram import Dispatcher
from aiogram.methods import SendPhoto
from aiogram.types import Message
from aiogram_dialog import setup_dialogs
from aiogram_dialog.test_tools import BotClient, MockMessageManager
from aiogram_dialog.test_tools.keyboard import InlineButtonTextLocator
from aiogram_dialog.test_tools.memory_storage import JsonMemoryStorage

from fake_bot import FakeSession, make_bot
from fake_games import FakeGameStateRepository
from fake_lobbies import FakeLobbyRepository
from fake_words import HINTS, WORD, FakeWord, FakeWords, catalog, pizza
from undercover.bot.routers.reveal import start_reveal
from undercover.bot.routers.setup_dialog import (
    MIN_CATEGORIES_TO_CHOOSE,
    Setup,
    create_setup_dialog,
)
from undercover.bot.routers.start import create_start_router
from undercover.db.repositories.words import CategoryOption, WordsRepository
from undercover.game.engine import (
    MAX_NAME_LENGTH,
    MAX_PLAYERS,
    MIN_PLAYERS,
    Catalog,
    max_spies_count,
)
from undercover.game.models import GameStatus
from undercover.texts import Buttons, Errors, Reveal
from undercover.texts import Setup as SetupTexts

CHAT_ID: Final = 100500
HOST_ID: Final = 777

CATEGORIES: Final = ("Города", "Еда", "Профессии")

NAMES: Final = (
    "Аня",
    "Борис",
    "Вера",
    "Галя",
    "Дима",
    "Егор",
    "Жанна",
    "Зина",
    "Игорь",
    "Кира",
    "Лёша",
    "Марина",
    "Никита",
    "Оля",
    "Пётр",
    "Рита",
)


@dataclass(frozen=True, slots=True)
class Table:
    client: BotClient
    messages: MockMessageManager
    games: FakeGameStateRepository
    words: FakeWords
    session: FakeSession

    async def send(self, text: str) -> None:
        await self.client.send(text)

    async def click(self, button_text: str) -> None:
        await self.client.click(self.screen, InlineButtonTextLocator(re.escape(button_text)))

    @property
    def screen(self) -> Message:
        return self.messages.last_message()

    @property
    def text(self) -> str:
        return self.screen.text or ""


@pytest.fixture
def words() -> FakeWords:
    return FakeWords(pizza())


@pytest.fixture
def picky_words() -> FakeWords:
    return FakeWords(pizza(), categories=catalog(*CATEGORIES))


async def open_table(words: FakeWords) -> Table:
    games = FakeGameStateRepository()
    dispatcher = Dispatcher(storage=JsonMemoryStorage(), games=games, lobbies=FakeLobbyRepository())
    dispatcher.include_router(create_start_router(words.open))
    dispatcher.include_router(create_setup_dialog(words.open, start_reveal))
    messages = MockMessageManager()
    setup_dialogs(dispatcher, message_manager=messages)

    session = FakeSession()
    table = Table(
        client=BotClient(dispatcher, user_id=HOST_ID, chat_id=CHAT_ID, bot=make_bot(session)),
        messages=messages,
        games=games,
        words=words,
        session=session,
    )
    await table.send("/start")
    return table


@pytest.fixture
async def table(words: FakeWords) -> Table:
    return await open_table(words)


@pytest.fixture
async def picky_table(picky_words: FakeWords) -> Table:
    return await open_table(picky_words)


def numbered(names: Sequence[str]) -> str:
    return "\n".join(f"{position}. {name}" for position, name in enumerate(names, 1))


def names_window(entered: int, players_count: int, *names: str) -> str:
    return SetupTexts.ASK_PLAYER_NAMES.format(
        entered=entered,
        players_count=players_count,
        names_list=numbered(names) if names else SetupTexts.NO_NAMES_YET,
    )


async def fill(
    table: Table, players_count: int, spies_count: int = 1, names: Sequence[str] | None = None
) -> list[str]:
    await table.send(str(players_count))
    await table.send(str(spies_count))
    chosen = list(names or NAMES[:players_count])
    for name in chosen:
        await table.send(name)
    if len(table.words.categories) >= MIN_CATEGORIES_TO_CHOOSE:
        await table.click(Buttons.CATEGORIES_DONE)
    return chosen


def test_the_dialog_opens_on_the_players_count() -> None:
    assert Setup.ask_players_count in Setup.__states__


async def test_start_asks_how_many_players(table: Table) -> None:
    assert SetupTexts.ASK_PLAYERS_COUNT in table.text


@pytest.mark.parametrize("players_count", [MIN_PLAYERS, 8, MAX_PLAYERS])
async def test_full_setup_ends_with_a_session_ready_to_deal(
    table: Table, players_count: int
) -> None:
    spies_count = max_spies_count(players_count)

    names = await fill(table, players_count, spies_count)
    await table.click(Buttons.PLAY)

    state = table.games.stored
    assert [player.name for player in state.players] == names
    assert [player.order_index for player in state.players] == list(range(players_count))
    assert sum(player.is_spy for player in state.players) == spies_count
    assert (state.chat_id, state.host_user_id) == (CHAT_ID, HOST_ID)
    assert state.status is GameStatus.REVEAL
    assert state.word_text == WORD
    assert set(state.hint_by_spy) == {p.order_index for p in state.players if p.is_spy}
    assert set(state.hint_by_spy.values()) <= set(HINTS)


async def test_the_deal_starts_right_after_the_play_button(table: Table) -> None:
    names = await fill(table, 4)

    await table.click(Buttons.PLAY)

    state = table.games.stored
    assert state.status is GameStatus.REVEAL
    assert state.reveal_cursor == 0

    (card,) = table.session.calls(SendPhoto)
    assert card.caption == Reveal.TURN_CAPTION.format(position=1, total=4, name=names[0])
    assert card.reply_markup is not None


async def test_confirmation_shows_the_deal_order(table: Table) -> None:
    names = await fill(table, 4, spies_count=1)

    assert (
        SetupTexts.CONFIRM_START.format(
            players_count=4,
            spies_count=1,
            chosen_categories=SetupTexts.ALL_CATEGORIES,
            names_list=numbered(names),
        )
        in table.text
    )


async def test_the_dictionary_is_opened_for_the_deal_and_released(table: Table) -> None:
    await fill(table, 4)
    before = table.words.opened

    assert table.words.closed == before

    await table.click(Buttons.PLAY)

    assert (table.words.opened, table.words.closed) == (before + 1, before + 1)


async def test_the_dialog_closes_after_the_game_is_built(table: Table) -> None:
    await fill(table, 4)
    await table.click(Buttons.PLAY)

    await table.send("Ещё один")

    assert table.games.saves == 1
    assert table.screen.reply_markup is None


async def test_the_name_counter_walks_through_the_whole_table(table: Table) -> None:
    await table.send("3")
    await table.send("1")

    assert names_window(0, 3) in table.text

    await table.send("Аня")

    assert names_window(1, 3, "Аня") in table.text


async def test_the_spies_question_knows_the_table_size(table: Table) -> None:
    await table.send("9")

    assert SetupTexts.ASK_SPIES_COUNT.format(players_count=9, max_spies=3) in table.text


@pytest.mark.parametrize("answer", ["много", "  ", "3.5", "-", "шесть"])
async def test_players_count_must_be_a_number(table: Table, answer: str) -> None:
    await table.send(answer)

    assert SetupTexts.NOT_A_NUMBER in table.text
    assert SetupTexts.ASK_PLAYERS_COUNT in table.text


@pytest.mark.parametrize("answer", [MIN_PLAYERS - 1, MAX_PLAYERS + 1, 0, -3, 100])
async def test_players_count_must_fit_the_rules(table: Table, answer: int) -> None:
    await table.send(str(answer))

    assert SetupTexts.BAD_PLAYERS_COUNT in table.text
    assert SetupTexts.ASK_PLAYERS_COUNT in table.text


async def test_a_rejected_count_does_not_move_the_dialog_on(table: Table) -> None:
    await table.send("17")
    await table.send("4")

    assert SetupTexts.ASK_SPIES_COUNT.format(players_count=4, max_spies=1) in table.text
    assert SetupTexts.BAD_PLAYERS_COUNT not in table.text


@pytest.mark.parametrize("answer", ["0", "3", "6", "-1"])
async def test_spies_count_must_leave_civilians_in_the_majority(table: Table, answer: str) -> None:
    await table.send("6")

    await table.send(answer)

    assert SetupTexts.BAD_SPIES_COUNT.format(players_count=6, max_spies=2) in table.text


async def test_spies_count_must_be_a_number(table: Table) -> None:
    await table.send("6")

    await table.send("парочка")

    assert SetupTexts.NOT_A_NUMBER in table.text
    assert SetupTexts.ASK_SPIES_COUNT.format(players_count=6, max_spies=2) in table.text


async def test_the_maximum_number_of_spies_is_accepted(table: Table) -> None:
    await table.send("6")

    await table.send("2")

    assert names_window(0, 6) in table.text


@pytest.mark.parametrize("answer", [" ", "\n", " \n  "])
async def test_a_player_needs_a_name(table: Table, answer: str) -> None:
    await table.send("3")
    await table.send("1")

    await table.send(answer)

    assert SetupTexts.EMPTY_NAME in table.text
    assert names_window(0, 3) in table.text


async def test_a_name_must_fit_on_the_card(table: Table) -> None:
    await table.send("3")
    await table.send("1")

    await table.send("А" * (MAX_NAME_LENGTH + 1))

    assert SetupTexts.TOO_LONG_NAME in table.text
    assert "1. " not in table.text


@pytest.mark.parametrize("twin", ["Аня", "аня", "  АНЯ  "])
async def test_two_players_cannot_share_a_name(table: Table, twin: str) -> None:
    await table.send("3")
    await table.send("1")
    await table.send("Аня")

    await table.send(twin)

    assert SetupTexts.DUPLICATE_NAME.format(name=twin.strip().replace("  ", " ")) in table.text
    assert names_window(1, 3, "Аня") in table.text


async def test_a_name_keeps_its_spelling_but_loses_extra_spaces(table: Table) -> None:
    await table.send("2")
    await table.send("1")

    await table.send("  Аня   Петрова\n")
    await table.send("Борис")
    await table.click(Buttons.PLAY)

    assert [player.name for player in table.games.stored.players] == ["Аня Петрова", "Борис"]


async def test_the_last_name_can_be_taken_back(table: Table) -> None:
    await table.send("3")
    await table.send("1")
    await table.send("Аня")
    await table.send("Опечатка")

    await table.click(Buttons.UNDO_NAME)

    assert names_window(1, 3, "Аня") in table.text


async def test_there_is_nothing_to_take_back_before_the_first_name(table: Table) -> None:
    await table.send("3")
    await table.send("1")

    with pytest.raises(ValueError, match="No button"):
        await table.click(Buttons.UNDO_NAME)


async def test_a_taken_back_name_can_be_used_again(table: Table) -> None:
    await table.send("2")
    await table.send("1")
    await table.send("Аня")
    await table.click(Buttons.UNDO_NAME)

    await table.send("Аня")

    assert SetupTexts.DUPLICATE_NAME.format(name="Аня") not in table.text
    assert names_window(1, 2, "Аня") in table.text


async def test_restart_wipes_the_draft(table: Table) -> None:
    await fill(table, 3, names=["Аня", "Борис", "Вера"])

    await table.click(Buttons.RESTART)

    assert SetupTexts.ASK_PLAYERS_COUNT in table.text

    await table.send("2")
    await table.send("1")

    assert names_window(0, 2) in table.text
    assert table.games.saves == 0


async def test_an_empty_dictionary_is_explained_and_the_draft_survives(table: Table) -> None:
    table.words.word = None
    names = await fill(table, 4)

    await table.click(Buttons.PLAY)

    assert Errors.EMPTY_CATALOG in table.text
    assert table.games.saves == 0

    table.words.word = pizza()
    await table.click(Buttons.PLAY)

    assert [player.name for player in table.games.stored.players] == names


async def test_a_word_without_hints_does_not_start_a_game(table: Table) -> None:
    table.words.word = FakeWord(id=1, text=WORD, hints=())
    await fill(table, 4)

    await table.click(Buttons.PLAY)

    assert Errors.EMPTY_CATALOG in table.text
    assert table.games.saves == 0


def ask_categories(chosen: str) -> str:
    return SetupTexts.ASK_CATEGORIES.format(chosen_categories=chosen)


def marked(title: str) -> str:
    return SetupTexts.CATEGORY_CHOSEN.format(item={"title": title})


async def test_a_table_without_categories_never_sees_the_question(table: Table) -> None:
    await fill(table, 3)

    assert SetupTexts.CONFIRM_START.split("\n")[0] in table.text
    assert "Откуда брать слово" not in table.text


async def test_a_single_category_is_not_worth_asking_about() -> None:
    table = await open_table(FakeWords(pizza(), categories=catalog("Еда")))

    await fill(table, 3)
    await table.click(Buttons.PLAY)

    assert table.games.stored.category_ids == []


async def test_the_question_comes_after_the_names(picky_table: Table) -> None:
    await picky_table.send("3")
    await picky_table.send("1")
    for name in NAMES[:3]:
        await picky_table.send(name)

    assert ask_categories(SetupTexts.ALL_CATEGORIES) in picky_table.text
    assert set(CATEGORIES) <= {text for text, _ in _buttons(picky_table)}


async def test_an_unmarked_choice_means_the_whole_dictionary(picky_table: Table) -> None:
    await fill(picky_table, 3)

    await picky_table.click(Buttons.PLAY)

    assert picky_table.games.stored.category_ids == []
    assert picky_table.words.asked_categories == [None]


async def test_marked_categories_reach_the_game(picky_table: Table) -> None:
    await picky_table.send("3")
    await picky_table.send("1")
    for name in NAMES[:3]:
        await picky_table.send(name)

    await picky_table.click("Города")
    await picky_table.click("Профессии")
    await picky_table.click(Buttons.CATEGORIES_DONE)
    await picky_table.click(Buttons.PLAY)

    assert sorted(picky_table.games.stored.category_ids) == [1, 3]
    assert picky_table.words.asked_categories[0] in (1, 3)


async def test_a_marked_category_can_be_unmarked(picky_table: Table) -> None:
    await picky_table.send("3")
    await picky_table.send("1")
    for name in NAMES[:3]:
        await picky_table.send(name)

    await picky_table.click("Еда")

    assert ask_categories("Еда") in picky_table.text

    await picky_table.click(marked("Еда"))

    assert ask_categories(SetupTexts.ALL_CATEGORIES) in picky_table.text


async def test_the_confirmation_names_the_chosen_categories(picky_table: Table) -> None:
    await picky_table.send("3")
    await picky_table.send("1")
    names = list(NAMES[:3])
    for name in names:
        await picky_table.send(name)

    await picky_table.click("Профессии")
    await picky_table.click("Города")
    await picky_table.click(Buttons.CATEGORIES_DONE)

    assert (
        SetupTexts.CONFIRM_START.format(
            players_count=3,
            spies_count=1,
            chosen_categories="Города, Профессии",
            names_list=numbered(names),
        )
        in picky_table.text
    )


async def test_restart_forgets_the_chosen_categories(picky_table: Table) -> None:
    await picky_table.send("3")
    await picky_table.send("1")
    for name in NAMES[:3]:
        await picky_table.send(name)
    await picky_table.click("Еда")
    await picky_table.click(Buttons.CATEGORIES_DONE)

    await picky_table.click(Buttons.RESTART)
    await fill(picky_table, 3)

    assert ask_categories(SetupTexts.ALL_CATEGORIES) not in picky_table.text

    await picky_table.click(Buttons.PLAY)

    assert picky_table.games.stored.category_ids == []


async def test_the_choice_can_be_reopened_from_the_confirmation(picky_table: Table) -> None:
    names = await fill(picky_table, 3)

    await picky_table.click(Buttons.CHANGE_CATEGORIES)

    assert ask_categories(SetupTexts.ALL_CATEGORIES) in picky_table.text

    await picky_table.click("Еда")
    await picky_table.click(Buttons.CATEGORIES_DONE)
    await picky_table.click(Buttons.PLAY)

    assert [player.name for player in picky_table.games.stored.players] == names
    assert picky_table.games.stored.category_ids == [2]


async def test_a_table_without_a_choice_has_nothing_to_reopen(table: Table) -> None:
    await fill(table, 3)

    with pytest.raises(ValueError, match="No button"):
        await table.click(Buttons.CHANGE_CATEGORIES)


async def test_categories_left_without_words_are_explained(picky_table: Table) -> None:
    picky_table.words.empty_categories = frozenset({1, 2, 3})
    await picky_table.send("3")
    await picky_table.send("1")
    for name in NAMES[:3]:
        await picky_table.send(name)
    await picky_table.click("Еда")
    await picky_table.click(Buttons.CATEGORIES_DONE)

    await picky_table.click(Buttons.PLAY)

    assert Errors.EMPTY_CATEGORIES in picky_table.text
    assert picky_table.games.saves == 0

    picky_table.words.empty_categories = frozenset()
    await picky_table.click(Buttons.CHANGE_CATEGORIES)
    await picky_table.click(Buttons.CATEGORIES_DONE)
    await picky_table.click(Buttons.PLAY)

    assert picky_table.games.saves == 1


def _buttons(table: Table) -> list[tuple[str, str]]:
    markup = table.screen.reply_markup
    assert markup is not None
    return [
        (button.text, button.callback_data or "")
        for row in markup.inline_keyboard
        for button in row
    ]


def test_words_repository_fits_the_catalog_protocol() -> None:
    expected = inspect.signature(Catalog.list_playable_categories)
    actual = inspect.signature(WordsRepository.list_playable_categories)

    assert actual.parameters == expected.parameters
    assert inspect.iscoroutinefunction(WordsRepository.list_playable_categories)
    assert all(hasattr(CategoryOption, name) for name in ("id", "title"))
