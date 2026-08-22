from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from undercover.db.models import GamePlayerResult, GameSessionLog
from undercover.game.models import GameSessionState, Winner


def _player_rows(state: GameSessionState, finished_at: datetime) -> list[GamePlayerResult]:
    if state.winner is None:
        return []
    return [
        GamePlayerResult(
            chat_id=state.chat_id,
            user_id=player.user_id,
            name=player.name,
            is_spy=player.is_spy,
            is_winner=(state.winner is Winner.SPIES) == player.is_spy,
            out_order=player.out_order,
            finished_at=finished_at,
        )
        for player in state.players
        if player.user_id is not None
    ]


class GameLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_finished(
        self, state: GameSessionState, finished_at: datetime | None = None
    ) -> None:
        at = finished_at or datetime.now(UTC)
        self._session.add(
            GameSessionLog(
                chat_id=state.chat_id,
                host_user_id=state.host_user_id,
                players_count=len(state.players),
                spies_count=sum(player.is_spy for player in state.players),
                word_id=state.word_id,
                winner=state.winner,
                started_at=state.created_at,
                finished_at=at,
                players=_player_rows(state, at),
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
