from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import datetime

from sqlalchemy import ColumnElement, Select, Text, and_, func, select
from sqlalchemy.dialects.postgresql import ARRAY, aggregate_order_by
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from undercover.db.models import GamePlayerResult, GameSessionLog
from undercover.game.models import Winner
from undercover.game.stats import (
    MIN_FIRST_OUTS,
    MIN_ROLE_GAMES,
    MIN_STREAK,
    MONTH_WINDOW,
    Champion,
    ChatTotals,
    HallOfFame,
    PlayerProfile,
)


def _streaks(chat_id: int, user_id: int | None = None) -> Select[tuple[str, int]]:
    rows = select(
        GamePlayerResult.user_id,
        GamePlayerResult.name,
        GamePlayerResult.is_winner,
        func.row_number()
        .over(
            partition_by=GamePlayerResult.user_id,
            order_by=(GamePlayerResult.finished_at.desc(), GamePlayerResult.id.desc()),
        )
        .label("position"),
    ).where(GamePlayerResult.chat_id == chat_id)
    if user_id is not None:
        rows = rows.where(GamePlayerResult.user_id == user_id)

    ranked = rows.subquery()
    position = ranked.c.position
    streak = (
        func.coalesce(func.min(position).filter(~ranked.c.is_winner), func.max(position) + 1) - 1
    )
    return select(
        func.min(ranked.c.name).filter(position == 1).label("name"),
        streak.label("streak"),
    ).group_by(ranked.c.user_id)


def _latest_name() -> ColumnElement[str]:
    ordered = aggregate_order_by(GamePlayerResult.name, GamePlayerResult.finished_at.desc())
    return func.array_agg(ordered, type_=ARRAY(Text))[1]


class StatsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def chat_totals(self, chat_id: int) -> ChatTotals:
        row = (
            await self._session.execute(
                select(
                    func.count().label("games"),
                    func.count()
                    .filter(GameSessionLog.winner == Winner.CIVILIANS)
                    .label("civilian_wins"),
                    func.count().filter(GameSessionLog.winner == Winner.SPIES).label("spy_wins"),
                ).where(GameSessionLog.chat_id == chat_id, GameSessionLog.winner.is_not(None))
            )
        ).one()
        return ChatTotals(games=row.games, civilian_wins=row.civilian_wins, spy_wins=row.spy_wins)

    async def player_profile(self, chat_id: int, user_id: int) -> PlayerProfile | None:
        row = (
            await self._session.execute(
                select(
                    func.count().label("games"),
                    func.count().filter(GamePlayerResult.is_winner).label("wins"),
                    func.count().filter(GamePlayerResult.is_spy).label("spy_games"),
                    func.count()
                    .filter(and_(GamePlayerResult.is_spy, GamePlayerResult.is_winner))
                    .label("spy_wins"),
                    func.count().filter(GamePlayerResult.out_order == 1).label("first_outs"),
                ).where(GamePlayerResult.chat_id == chat_id, GamePlayerResult.user_id == user_id)
            )
        ).one()
        if not row.games:
            return None

        return PlayerProfile(
            games=row.games,
            wins=row.wins,
            spy_games=row.spy_games,
            spy_wins=row.spy_wins,
            streak=await self._streak_of(chat_id, user_id),
            first_outs=row.first_outs,
        )

    async def _role_champion(
        self, chat_id: int, *, is_spy: bool, since: datetime | None = None
    ) -> Champion | None:
        games = func.count()
        wins = func.count().filter(GamePlayerResult.is_winner)
        name = _latest_name()

        query = (
            select(name.label("name"), wins.label("wins"), games.label("games"))
            .where(GamePlayerResult.chat_id == chat_id, GamePlayerResult.is_spy == is_spy)
            .group_by(GamePlayerResult.user_id)
            .having(games >= MIN_ROLE_GAMES, wins > 0)
            .order_by((wins * 1.0 / games).desc(), games.desc(), name)
            .limit(1)
        )
        if since is not None:
            query = query.where(GamePlayerResult.finished_at >= since)

        row = (await self._session.execute(query)).first()
        return None if row is None else Champion(name=row.name, value=row.wins, total=row.games)

    async def _first_victim(self, chat_id: int) -> Champion | None:
        first_outs = func.count().filter(GamePlayerResult.out_order == 1)
        name = _latest_name()

        row = (
            await self._session.execute(
                select(name.label("name"), first_outs.label("first_outs"))
                .where(GamePlayerResult.chat_id == chat_id)
                .group_by(GamePlayerResult.user_id)
                .having(first_outs >= MIN_FIRST_OUTS)
                .order_by(first_outs.desc(), func.count().asc(), name)
                .limit(1)
            )
        ).first()
        return None if row is None else Champion(name=row.name, value=row.first_outs)

    async def _longest_streak(self, chat_id: int) -> Champion | None:
        totals = _streaks(chat_id).subquery()
        row = (
            await self._session.execute(
                select(totals.c.name, totals.c.streak)
                .where(totals.c.streak >= MIN_STREAK)
                .order_by(totals.c.streak.desc(), totals.c.name)
                .limit(1)
            )
        ).first()
        return None if row is None else Champion(name=row.name, value=int(row.streak))

    async def hall_of_fame(self, chat_id: int, now: datetime) -> HallOfFame:
        return HallOfFame(
            totals=await self.chat_totals(chat_id),
            spy_of_the_month=await self._role_champion(
                chat_id, is_spy=True, since=now - MONTH_WINDOW
            ),
            best_detective=await self._role_champion(chat_id, is_spy=False),
            first_victim=await self._first_victim(chat_id),
            longest_streak=await self._longest_streak(chat_id),
        )

    async def _streak_of(self, chat_id: int, user_id: int) -> int:
        found = (await self._session.execute(_streaks(chat_id, user_id))).first()
        return 0 if found is None else int(found.streak)


def stats_source(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> Callable[[], AbstractAsyncContextManager[StatsRepository]]:
    @asynccontextmanager
    async def open_stats() -> AsyncGenerator[StatsRepository]:
        async with sessionmaker() as session:
            yield StatsRepository(session)

    return open_stats
