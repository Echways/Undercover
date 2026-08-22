from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from undercover.db.models import Category, GameSessionLog, SpyHint, Word
from undercover.db.repositories.game_log import GameLogRepository, game_log_writer
from undercover.game.models import GameSessionState, GameStatus, PlayerState, Winner

pytestmark = pytest.mark.integration

CHAT_ID = -100500
HOST_ID = 777
STARTED_AT = datetime(2026, 8, 21, 18, 0, tzinfo=UTC)
FINISHED_AT = STARTED_AT + timedelta(minutes=17)

NAMES = ("Аня", "Борис", "Вера", "Галя")
SPY_INDEXES = (1, 3)


async def add_word(session: AsyncSession, text: str = "пицца") -> Word:
    word = Word(text=text, hints=[SpyHint(hint_text="её режут на куски")])
    session.add(Category(slug=f"food-{text}", title="Еда", words=[word]))
    await session.flush()
    return word


def make_state(word_id: int, **overrides: object) -> GameSessionState:
    defaults: dict[str, object] = {
        "session_id": "11111111-1111-1111-1111-111111111111",
        "chat_id": CHAT_ID,
        "host_user_id": HOST_ID,
        "status": GameStatus.FINISHED,
        "players": [
            PlayerState(order_index=index, name=name, is_spy=index in SPY_INDEXES)
            for index, name in enumerate(NAMES)
        ],
        "word_id": word_id,
        "word_text": "пицца",
        "created_at": STARTED_AT,
    }
    return GameSessionState.model_validate(defaults | overrides)


async def stored_rows(session: AsyncSession) -> list[GameSessionLog]:
    result = await session.execute(select(GameSessionLog).where(GameSessionLog.chat_id == CHAT_ID))
    return list(result.scalars())


async def test_finished_game_is_recorded_as_a_single_row(db_session: AsyncSession) -> None:
    word = await add_word(db_session)

    await GameLogRepository(db_session).record_finished(make_state(word.id), FINISHED_AT)

    (row,) = await stored_rows(db_session)
    assert (row.chat_id, row.host_user_id) == (CHAT_ID, HOST_ID)
    assert (row.players_count, row.spies_count) == (len(NAMES), len(SPY_INDEXES))
    assert row.word_id == word.id
    assert row.started_at == STARTED_AT
    assert row.finished_at == FINISHED_AT


async def test_finish_time_defaults_to_now(db_session: AsyncSession) -> None:
    word = await add_word(db_session)
    before = datetime.now(UTC)

    await GameLogRepository(db_session).record_finished(make_state(word.id))

    (row,) = await stored_rows(db_session)
    assert row.finished_at is not None
    assert before <= row.finished_at <= datetime.now(UTC)


async def test_every_game_gets_its_own_row(db_session: AsyncSession) -> None:
    word = await add_word(db_session)
    repository = GameLogRepository(db_session)

    await repository.record_finished(make_state(word.id))
    await repository.record_finished(
        make_state(word.id, session_id="22222222-2222-2222-2222-222222222222")
    )

    assert len(await stored_rows(db_session)) == 2


async def test_a_won_game_records_its_winner(db_session: AsyncSession) -> None:
    word = await add_word(db_session)

    await GameLogRepository(db_session).record_finished(make_state(word.id, winner=Winner.SPIES))

    (row,) = await stored_rows(db_session)
    assert row.winner == Winner.SPIES


async def test_a_game_ended_early_records_no_winner(db_session: AsyncSession) -> None:
    word = await add_word(db_session)

    await GameLogRepository(db_session).record_finished(make_state(word.id))

    (row,) = await stored_rows(db_session)
    assert row.winner is None


async def test_a_word_missing_from_the_catalog_is_reported(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        await GameLogRepository(db_session).record_finished(make_state(word_id=10**9))


@pytest.fixture
async def sessionmaker(migrated_dsn: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_dsn)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                delete(GameSessionLog).where(GameSessionLog.chat_id == CHAT_ID)
            )
            await connection.execute(delete(Category).where(Category.slug == "food-пицца"))
        await engine.dispose()


async def test_writer_commits_the_record(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker.begin() as session:
        word = await add_word(session)
        word_id = word.id

    await game_log_writer(sessionmaker)(make_state(word_id))

    async with sessionmaker() as session:
        (row,) = await stored_rows(session)
        assert row.word_id == word_id
