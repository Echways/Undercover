import inspect
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from random import Random
from typing import Any

import pytest

from undercover.db.models import SpyHint, Word
from undercover.db.repositories.words import WordsRepository
from undercover.game.engine import (
    MAX_PLAYERS,
    MIN_PLAYERS,
    EmptyWordCatalogError,
    GameRulesError,
    WordsSource,
    assign_hints,
    assign_roles,
    build_discussion_order,
    create_session,
    max_spies_count,
    pick_word,
)
from undercover.game.models import GameSessionState, GameStatus, PlayerState, WordWithHints

SEED = 20260821


def test_game_core_pulls_in_neither_telegram_nor_the_database() -> None:
    probe = (
        "import sys; import undercover.game.engine, undercover.game.models; "
        "print(sorted(m for m in sys.modules if m in {'aiogram', 'sqlalchemy', 'redis'}))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )

    assert completed.stdout.strip() == "[]"


def rng() -> Random:
    return Random(SEED)


def names(count: int) -> list[str]:
    return [f"Игрок-{index}" for index in range(count)]


def test_keeps_input_order_and_numbers_players_from_zero() -> None:
    players = assign_roles(["Аня", "Боря", "Вера", "Гена"], spies_count=1, rng=rng())

    assert [player.name for player in players] == ["Аня", "Боря", "Вера", "Гена"]
    assert [player.order_index for player in players] == [0, 1, 2, 3]


@pytest.mark.parametrize("players_count", range(MIN_PLAYERS, MAX_PLAYERS + 1))
def test_assigns_exactly_the_requested_number_of_spies(players_count: int) -> None:
    generator = rng()
    for spies_count in range(1, max_spies_count(players_count) + 1):
        players = assign_roles(names(players_count), spies_count, generator)

        assert sum(player.is_spy for player in players) == spies_count
        assert len(players) == players_count


def test_spies_are_not_always_the_same_players() -> None:
    generator = rng()
    spies = {
        player.order_index
        for _ in range(300)
        for player in assign_roles(names(6), 1, generator)
        if player.is_spy
    }

    assert spies == set(range(6))


def test_same_seed_gives_the_same_deal() -> None:
    assert assign_roles(names(8), 2, Random(7)) == assign_roles(names(8), 2, Random(7))


def test_all_players_are_civilians_except_the_spies() -> None:
    players = assign_roles(names(6), 2, rng())

    assert sum(not player.is_spy for player in players) == 4


@pytest.mark.parametrize("players_count", [MIN_PLAYERS - 1, MAX_PLAYERS + 1])
def test_rejects_players_count_outside_the_rules(players_count: int) -> None:
    with pytest.raises(GameRulesError):
        assign_roles(names(players_count), 1, rng())


@pytest.mark.parametrize("players_count", range(MIN_PLAYERS, MAX_PLAYERS + 1))
def test_accepts_the_maximum_allowed_number_of_spies(players_count: int) -> None:
    limit = max_spies_count(players_count)
    players = assign_roles(names(players_count), limit, rng())

    assert sum(player.is_spy for player in players) == limit
    with pytest.raises(GameRulesError):
        assign_roles(names(players_count), limit + 1, rng())


@pytest.mark.parametrize("spies_count", [0, -1])
def test_rejects_a_game_without_spies(spies_count: int) -> None:
    with pytest.raises(GameRulesError):
        assign_roles(names(6), spies_count, rng())


@pytest.mark.parametrize("players_count", range(MIN_PLAYERS, MAX_PLAYERS + 1))
def test_spies_never_outnumber_or_equal_civilians_at_the_limit(players_count: int) -> None:
    limit = max_spies_count(players_count)
    civilians = players_count - limit

    assert limit >= 1
    if players_count == MIN_PLAYERS:
        assert civilians == limit
    else:
        assert civilians > limit


def test_discussion_order_is_a_permutation_of_the_same_players() -> None:
    players = assign_roles(names(9), 2, rng())

    order = build_discussion_order(players, rng())

    assert sorted(order) == [player.order_index for player in players]


def test_discussion_order_does_not_change_the_players() -> None:
    players = assign_roles(names(6), 2, rng())
    snapshot = list(players)

    build_discussion_order(players, rng())

    assert players == snapshot


def test_discussion_order_does_not_repeat_the_deal_order() -> None:
    players = assign_roles(names(6), 1, rng())
    deal_order = tuple(player.order_index for player in players)
    generator = rng()

    orders = [tuple(build_discussion_order(players, generator)) for _ in range(300)]

    assert sum(order == deal_order for order in orders) < 10
    assert len(set(orders)) > 100


def test_every_player_can_speak_first() -> None:
    players = assign_roles(names(6), 1, rng())
    generator = rng()

    first_speakers = {build_discussion_order(players, generator)[0] for _ in range(300)}

    assert first_speakers == {player.order_index for player in players}


def test_same_seed_gives_the_same_discussion_order() -> None:
    players = assign_roles(names(8), 2, rng())

    assert build_discussion_order(players, Random(7)) == build_discussion_order(players, Random(7))


def test_discussion_order_of_two_players_holds_both() -> None:
    players = assign_roles(names(2), 1, rng())

    assert sorted(build_discussion_order(players, rng())) == [0, 1]


def test_rejects_an_empty_discussion() -> None:
    with pytest.raises(GameRulesError):
        build_discussion_order([], rng())


@dataclass(frozen=True, slots=True)
class FakeHint:
    hint_text: str


@dataclass(frozen=True, slots=True)
class FakeWord:
    id: int
    text: str
    hints: list[FakeHint]


@dataclass(slots=True)
class FakeWordsSource:
    catalog: dict[int | None, FakeWord]
    calls: list[int | None] = field(default_factory=list)

    async def get_random_active_word(self, category_id: int | None = None) -> FakeWord | None:
        self.calls.append(category_id)
        return self.catalog.get(category_id)


def pizza(word_id: int = 1) -> FakeWord:
    return FakeWord(
        id=word_id,
        text="пицца",
        hints=[FakeHint("её режут на куски"), FakeHint("её заказывают домой")],
    )


async def test_returns_the_word_with_its_hints() -> None:
    source = FakeWordsSource({None: pizza(word_id=42)})

    word = await pick_word(source, category_ids=None, rng=rng())

    assert word == WordWithHints(
        word_id=42, text="пицца", hints=["её режут на куски", "её заказывают домой"]
    )


async def test_asks_for_any_category_when_none_requested() -> None:
    source = FakeWordsSource({None: pizza()})

    await pick_word(source, category_ids=None, rng=rng())

    assert source.calls == [None]


async def test_treats_an_empty_category_list_as_no_restriction() -> None:
    source = FakeWordsSource({None: pizza()})

    await pick_word(source, category_ids=[], rng=rng())

    assert source.calls == [None]


async def test_picks_one_of_the_requested_categories_at_random() -> None:
    catalog: dict[int | None, FakeWord] = {
        category_id: FakeWord(category_id, f"слово-{category_id}", [FakeHint("подсказка")])
        for category_id in (1, 2, 3)
    }
    generator = rng()

    picked = set()
    for _ in range(100):
        source = FakeWordsSource(dict(catalog))
        picked.add((await pick_word(source, [1, 2, 3], generator)).text)
        assert len(source.calls) == 1

    assert picked == {"слово-1", "слово-2", "слово-3"}


async def test_falls_back_to_another_category_when_the_chosen_one_is_empty() -> None:
    generator = rng()
    attempts = set()

    for _ in range(50):
        source = FakeWordsSource({2: pizza()})

        word = await pick_word(source, [1, 2], generator)

        assert word.text == "пицца"
        assert source.calls[-1] == 2
        attempts.add(len(source.calls))

    assert attempts == {1, 2}


async def test_raises_when_no_requested_category_has_words() -> None:
    source = FakeWordsSource({})

    with pytest.raises(EmptyWordCatalogError):
        await pick_word(source, [1, 2], rng=rng())

    assert set(source.calls) == {1, 2}


async def test_raises_on_an_empty_catalog() -> None:
    source = FakeWordsSource({})

    with pytest.raises(EmptyWordCatalogError):
        await pick_word(source, category_ids=None, rng=rng())


async def test_word_without_hints_is_returned_with_an_empty_hint_list() -> None:
    source = FakeWordsSource({None: FakeWord(1, "пицца", [])})

    word = await pick_word(source, category_ids=None, rng=rng())

    assert word.hints == ()


def test_players_of_a_deal_can_be_reused_for_the_discussion() -> None:
    players: Sequence[PlayerState] = assign_roles(names(4), 1, rng())

    assert len(build_discussion_order(players, rng())) == 4


def word_with(*hints: str) -> WordWithHints:
    return WordWithHints(word_id=1, text="пицца", hints=hints)


def test_every_spy_gets_a_hint_and_civilians_get_none() -> None:
    players = assign_roles(names(9), spies_count=3, rng=rng())

    hints = assign_hints(players, word_with("а", "б", "в"), rng())

    assert set(hints) == {player.order_index for player in players if player.is_spy}


def test_spies_get_different_hints_while_there_are_enough() -> None:
    players = assign_roles(names(16), spies_count=5, rng=rng())
    generator = rng()

    for _ in range(50):
        hints = assign_hints(players, word_with("а", "б", "в", "г", "д"), generator)

        assert len(set(hints.values())) == 5


def test_hints_repeat_only_when_there_are_fewer_of_them_than_spies() -> None:
    players = assign_roles(names(16), spies_count=5, rng=rng())

    hints = assign_hints(players, word_with("а", "б"), rng())

    assert len(hints) == 5
    assert set(hints.values()) == {"а", "б"}


def test_hint_is_not_always_the_same_one() -> None:
    players = assign_roles(names(6), spies_count=1, rng=rng())
    generator = rng()

    picked = {
        next(iter(assign_hints(players, word_with("а", "б", "в"), generator).values()))
        for _ in range(100)
    }

    assert picked == {"а", "б", "в"}


def test_rejects_a_word_without_hints() -> None:
    players = assign_roles(names(6), spies_count=1, rng=rng())

    with pytest.raises(EmptyWordCatalogError):
        assign_hints(players, word_with(), rng())


def test_rejects_a_deal_without_spies() -> None:
    players = [
        PlayerState(order_index=index, name=name, is_spy=False)
        for index, name in enumerate(names(4))
    ]

    with pytest.raises(GameRulesError):
        assign_hints(players, word_with("а"), rng())


async def make_session(
    players_count: int = 6,
    spies_count: int = 1,
    generator: Random | None = None,
    **overrides: Any,
) -> GameSessionState:
    defaults: dict[str, Any] = {
        "chat_id": -100500,
        "host_user_id": 777,
        "player_names": names(players_count),
        "spies_count": spies_count,
        "words": FakeWordsSource({None: pizza(word_id=42)}),
        "rng": generator or rng(),
    }
    return await create_session(**(defaults | overrides))


@pytest.mark.parametrize("players_count", [MIN_PLAYERS, 8, MAX_PLAYERS])
async def test_assembles_a_playable_session(players_count: int) -> None:
    spies_count = max_spies_count(players_count)

    state = await make_session(players_count, spies_count)

    assert state.status is GameStatus.SETUP
    assert [player.name for player in state.players] == names(players_count)
    assert sum(player.is_spy for player in state.players) == spies_count
    assert (state.word_id, state.word_text) == (42, "пицца")
    assert set(state.hint_by_spy) == {p.order_index for p in state.players if p.is_spy}


async def test_remembers_the_chosen_categories() -> None:
    source = FakeWordsSource({2: pizza(word_id=42)})

    state = await make_session(words=source, category_ids=[2])

    assert state.category_ids == [2]


async def test_a_session_without_a_choice_keeps_the_whole_catalog() -> None:
    state = await make_session()

    assert state.category_ids == []


async def test_keeps_the_host_and_the_chat_of_the_setup() -> None:
    state = await make_session(chat_id=-4242, host_user_id=13)

    assert (state.chat_id, state.host_user_id) == (-4242, 13)


async def test_session_starts_before_the_first_card_is_dealt() -> None:
    state = await make_session()

    assert state.reveal_cursor == 0
    assert state.discussion_order == []
    assert state.current_message_id is None
    assert not any(player.has_viewed for player in state.players)


async def test_every_session_gets_its_own_id() -> None:
    generator = rng()

    ids = {(await make_session(generator=generator)).session_id for _ in range(100)}

    assert len(ids) == 100
    assert all(len(session_id) == 36 for session_id in ids)


async def test_same_seed_gives_the_same_session() -> None:
    first = await make_session(generator=Random(7))
    second = await make_session(generator=Random(7))

    assert first.model_dump(exclude={"created_at"}) == second.model_dump(exclude={"created_at"})


async def test_refuses_a_composition_against_the_rules() -> None:
    with pytest.raises(GameRulesError):
        await make_session(players_count=6, spies_count=99)


async def test_refuses_to_start_without_a_word() -> None:
    with pytest.raises(EmptyWordCatalogError):
        await make_session(words=FakeWordsSource({}))


async def test_refuses_to_start_when_the_word_has_no_hints() -> None:
    source = FakeWordsSource({None: FakeWord(1, "пицца", [])})

    with pytest.raises(EmptyWordCatalogError):
        await make_session(words=source)


def test_words_repository_fits_the_words_source_protocol() -> None:
    expected = inspect.signature(WordsSource.get_random_active_word)
    actual = inspect.signature(WordsRepository.get_random_active_word)

    assert actual.parameters == expected.parameters
    assert inspect.iscoroutinefunction(WordsRepository.get_random_active_word)
    assert all(hasattr(Word, name) for name in ("id", "text", "hints"))
    assert hasattr(SpyHint, "hint_text")
