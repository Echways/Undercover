from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession

from undercover.db.models import Category, SpyHint, Word
from undercover.db.repositories.words import WordsRepository

pytestmark = pytest.mark.integration


@contextmanager
def executed_statements() -> Iterator[list[str]]:
    statements: list[str] = []

    def record(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(Engine, "before_cursor_execute", record)


async def add_category(
    session: AsyncSession,
    slug: str,
    words: dict[str, list[str]],
    *,
    is_active: bool = True,
    words_active: bool = True,
) -> Category:
    category = Category(
        slug=slug,
        title=slug.capitalize(),
        is_active=is_active,
        words=[
            Word(
                text=text,
                is_active=words_active,
                hints=[SpyHint(hint_text=hint) for hint in hints],
            )
            for text, hints in words.items()
        ],
    )
    session.add(category)
    await session.flush()
    return category


async def test_returns_active_word_with_its_hints(db_session: AsyncSession) -> None:
    await add_category(db_session, "food", {"пицца": ["её режут на куски", "её заказывают"]})

    word = await WordsRepository(db_session).get_random_active_word()

    assert word is not None
    assert word.text == "пицца"
    assert [hint.hint_text for hint in word.hints] == ["её режут на куски", "её заказывают"]


async def test_loads_word_and_hints_in_single_query(db_session: AsyncSession) -> None:
    await add_category(db_session, "food", {"пицца": ["её режут на куски", "её заказывают"]})

    with executed_statements() as statements:
        word = await WordsRepository(db_session).get_random_active_word()
        assert word is not None
        assert len(word.hints) == 2

    assert len(statements) == 1, statements


async def test_filters_by_category(db_session: AsyncSession) -> None:
    food = await add_category(db_session, "food", {"пицца": ["её режут на куски"]})
    await add_category(db_session, "cities", {"Париж": ["там башня"]})

    repository = WordsRepository(db_session)

    picked = await repository.get_random_active_word(category_id=food.id)

    assert picked is not None
    assert picked.text == "пицца"


async def test_ignores_inactive_words(db_session: AsyncSession) -> None:
    await add_category(db_session, "food", {"пицца": ["её режут"]}, words_active=False)
    await add_category(db_session, "cities", {"Париж": ["там башня"]})

    word = await WordsRepository(db_session).get_random_active_word()

    assert word is not None
    assert word.text == "Париж"


async def test_ignores_words_of_inactive_category(db_session: AsyncSession) -> None:
    await add_category(db_session, "food", {"пицца": ["её режут"]}, is_active=False)
    await add_category(db_session, "cities", {"Париж": ["там башня"]})

    word = await WordsRepository(db_session).get_random_active_word()

    assert word is not None
    assert word.text == "Париж"


async def test_returns_none_when_category_has_no_active_words(db_session: AsyncSession) -> None:
    food = await add_category(db_session, "food", {"пицца": ["её режут"]}, words_active=False)

    assert await WordsRepository(db_session).get_random_active_word(food.id) is None


async def test_returns_none_on_empty_catalog(db_session: AsyncSession) -> None:
    assert await WordsRepository(db_session).get_random_active_word() is None


async def test_picks_different_words_across_calls(db_session: AsyncSession) -> None:
    await add_category(db_session, "food", {text: ["подсказка"] for text in "абвгд"})
    repository = WordsRepository(db_session)

    words = [await repository.get_random_active_word() for _ in range(30)]

    assert all(word is not None for word in words)
    assert len({word.text for word in words if word is not None}) > 1
