from collections.abc import Callable, Sequence, Sized
from contextlib import AbstractAsyncContextManager
from random import Random, SystemRandom
from typing import Final, Protocol
from uuid import UUID

from undercover.game.models import (
    GameMode,
    GameSessionState,
    GameStatus,
    PlayerState,
    WordWithHints,
)

MIN_PLAYERS: Final = 2
MAX_PLAYERS: Final = 16
MAX_NAME_LENGTH: Final = 24
MIN_CATEGORIES_TO_CHOOSE: Final = 2


class GameRulesError(ValueError):
    pass


class EmptyWordCatalogError(RuntimeError):
    pass


class HintRecord(Protocol):
    @property
    def hint_text(self) -> str: ...


class WordRecord(Protocol):
    @property
    def id(self) -> int: ...

    @property
    def text(self) -> str: ...

    @property
    def hints(self) -> Sequence[HintRecord]: ...


class WordsSource(Protocol):
    async def get_random_active_word(self, category_id: int | None = None) -> WordRecord | None: ...


class CategoryRecord(Protocol):
    @property
    def id(self) -> int: ...

    @property
    def title(self) -> str: ...


class Catalog(WordsSource, Protocol):
    async def list_playable_categories(self) -> Sequence[CategoryRecord]: ...


CatalogFactory = Callable[[], AbstractAsyncContextManager[Catalog]]
WordsSourceFactory = Callable[[], AbstractAsyncContextManager[WordsSource]]


def offers_a_choice(categories: Sized) -> bool:
    return len(categories) >= MIN_CATEGORIES_TO_CHOOSE


def secure_rng() -> Random:
    return SystemRandom()


def max_spies_count(players_count: int) -> int:
    return max(1, players_count // 3)


def assign_roles(
    player_names: Sequence[str],
    spies_count: int,
    rng: Random,
    player_ids: Sequence[int] | None = None,
) -> list[PlayerState]:
    players_count = len(player_names)
    if not MIN_PLAYERS <= players_count <= MAX_PLAYERS:
        raise GameRulesError(
            f"игроков должно быть от {MIN_PLAYERS} до {MAX_PLAYERS}, а не {players_count}"
        )

    ids: tuple[int | None, ...] = (
        tuple(player_ids) if player_ids is not None else (None,) * players_count
    )
    if len(ids) != players_count:
        raise GameRulesError(
            f"идентификаторов {len(ids)}, а игроков {players_count} — состав не сходится"
        )

    limit = max_spies_count(players_count)
    if not 1 <= spies_count <= limit:
        raise GameRulesError(
            f"шпионов на {players_count} игроков должно быть от 1 до {limit}, а не {spies_count}"
        )

    spies = set(rng.sample(range(players_count), spies_count))
    return [
        PlayerState(
            order_index=order_index,
            name=name,
            is_spy=order_index in spies,
            user_id=ids[order_index],
        )
        for order_index, name in enumerate(player_names)
    ]


def build_discussion_order(players: Sequence[PlayerState], rng: Random) -> list[int]:
    if not players:
        raise GameRulesError("обсуждать нечего: в партии нет игроков")

    order = [player.order_index for player in players]
    rng.shuffle(order)
    return order


async def pick_word(
    words: WordsSource, category_ids: Sequence[int] | None, rng: Random
) -> WordWithHints:
    candidates: list[int | None] = list(category_ids) if category_ids else [None]
    rng.shuffle(candidates)

    for category_id in candidates:
        found = await words.get_random_active_word(category_id=category_id)
        if found is not None:
            return WordWithHints(
                word_id=found.id,
                text=found.text,
                hints=tuple(hint.hint_text for hint in found.hints),
            )

    raise EmptyWordCatalogError(
        "в словаре нет активных слов"
        if category_ids is None
        else f"в категориях {sorted(category_ids)} нет активных слов"
    )


def assign_hints(
    players: Sequence[PlayerState], word: WordWithHints, rng: Random
) -> dict[int, str]:
    spies = [player.order_index for player in players if player.is_spy]
    if not spies:
        raise GameRulesError("в партии нет ни одного шпиона")
    if not word.hints:
        raise EmptyWordCatalogError(f"у слова «{word.text}» нет ни одной подсказки шпиону")

    pool = list(word.hints)
    rng.shuffle(pool)
    return {spy: pool[position % len(pool)] for position, spy in enumerate(spies)}


async def create_session(
    *,
    chat_id: int,
    host_user_id: int,
    player_names: Sequence[str],
    spies_count: int,
    words: WordsSource,
    rng: Random,
    category_ids: Sequence[int] | None = None,
    player_ids: Sequence[int] | None = None,
    mode: GameMode = GameMode.HOT_SEAT,
    turn_seconds: int = 0,
) -> GameSessionState:
    players = assign_roles(player_names, spies_count, rng, player_ids)
    word = await pick_word(words, category_ids, rng)
    return GameSessionState(
        session_id=str(UUID(int=rng.getrandbits(128), version=4)),
        chat_id=chat_id,
        host_user_id=host_user_id,
        mode=mode,
        turn_seconds=turn_seconds,
        status=GameStatus.SETUP,
        players=players,
        word_id=word.word_id,
        word_text=word.text,
        category_ids=list(category_ids or ()),
        hint_by_spy=assign_hints(players, word, rng),
    )
