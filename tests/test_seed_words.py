import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from undercover.db.models import Category, SpyHint, Word
from undercover.db.repositories.words import WordsRepository
from undercover.db.seed import seed_words

pytestmark = pytest.mark.integration


async def catalog_counts(session: AsyncSession) -> tuple[int, int, int]:
    counts = [
        await session.scalar(select(func.count()).select_from(model)) or 0
        for model in (Category, Word, SpyHint)
    ]
    return counts[0], counts[1], counts[2]


async def test_seeds_categories_words_and_hints(db_session: AsyncSession) -> None:
    report = await seed_words(db_session)

    assert (report.categories, report.words, report.hints) == await catalog_counts(db_session)
    assert report.categories >= 3


async def test_every_category_has_eight_to_ten_words(db_session: AsyncSession) -> None:
    await seed_words(db_session)

    counts = (
        (await db_session.execute(select(func.count(Word.id)).group_by(Word.category_id)))
        .scalars()
        .all()
    )

    assert counts and all(8 <= count <= 10 for count in counts), counts


async def test_every_word_has_two_to_three_hints(db_session: AsyncSession) -> None:
    await seed_words(db_session)

    counts = (
        (await db_session.execute(select(func.count(SpyHint.id)).group_by(SpyHint.word_id)))
        .scalars()
        .all()
    )

    assert len(counts) == await db_session.scalar(select(func.count()).select_from(Word))
    assert all(2 <= count <= 3 for count in counts), counts


async def test_second_run_changes_nothing(db_session: AsyncSession) -> None:
    await seed_words(db_session)
    before = await catalog_counts(db_session)

    await seed_words(db_session)

    assert await catalog_counts(db_session) == before


async def test_second_run_restores_edited_title(db_session: AsyncSession) -> None:
    await seed_words(db_session)
    slug = await db_session.scalar(select(Category.slug).order_by(Category.id).limit(1))
    await db_session.execute(update(Category).where(Category.slug == slug).values(title="сломано"))

    await seed_words(db_session)

    assert await db_session.scalar(select(Category.title).where(Category.slug == slug)) != "сломано"


async def test_second_run_keeps_word_disabled_by_operator(db_session: AsyncSession) -> None:
    await seed_words(db_session)
    word_id = await db_session.scalar(select(Word.id).order_by(Word.id).limit(1))
    await db_session.execute(update(Word).where(Word.id == word_id).values(is_active=False))

    await seed_words(db_session)

    assert await db_session.scalar(select(Word.is_active).where(Word.id == word_id)) is False


async def test_seeded_word_is_playable(db_session: AsyncSession) -> None:
    await seed_words(db_session)

    word = await WordsRepository(db_session).get_random_active_word()

    assert word is not None
    assert word.text
    assert 2 <= len(word.hints) <= 3
