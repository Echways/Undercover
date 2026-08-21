from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import joinedload

from undercover.db.models import Category, Word


class WordsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
