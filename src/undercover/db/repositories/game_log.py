from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from undercover.db.models import GameSessionLog
from undercover.game.models import GameSessionState


class GameLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_finished(
        self, state: GameSessionState, finished_at: datetime | None = None
    ) -> None:
        self._session.add(
            GameSessionLog(
                chat_id=state.chat_id,
                host_user_id=state.host_user_id,
                players_count=len(state.players),
                spies_count=sum(player.is_spy for player in state.players),
                word_id=state.word_id,
                started_at=state.created_at,
                finished_at=finished_at or datetime.now(UTC),
            )
        )
        await self._session.flush()


def game_log_writer(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> Callable[[GameSessionState], Awaitable[None]]:
    async def write(state: GameSessionState) -> None:
        async with sessionmaker.begin() as session:
            await GameLogRepository(session).record_finished(state)

    return write
