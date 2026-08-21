from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import joinedload

from undercover.db.models import Category, Word


@dataclass(frozen=True, slots=True)
class CategoryOption:
    id: int
    title: str


class WordsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_playable_categories(self) -> Sequence[CategoryOption]:
        result = await self._session.execute(
            select(Category.id, Category.title)
            .where(Category.is_active, Category.words.any(Word.is_active))
            .order_by(Category.title)
        )
        return [CategoryOption(id=row.id, title=row.title) for row in result]

    async def get_random_active_word(self, category_id: int | None = None) -> Word | None:
        candidate = (
            select(Word.id)
            .join(Word.category)
            .where(Word.is_active, Category.is_active)
            .order_by(func.random())
            .limit(1)
        )
        if category_id is not None:
            candidate = candidate.where(Word.category_id == category_id)

        result = await self._session.execute(
            select(Word)
            .where(Word.id == candidate.scalar_subquery())
            .options(joinedload(Word.hints))
        )
        return result.unique().scalar_one_or_none()


def words_source(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> Callable[[], AbstractAsyncContextManager[WordsRepository]]:
    @asynccontextmanager
    async def open_words() -> AsyncIterator[WordsRepository]:
        async with sessionmaker() as session:
            yield WordsRepository(session)

    return open_words
