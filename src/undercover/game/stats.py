from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Protocol

MIN_ROLE_GAMES: Final = 3
MIN_FIRST_OUTS: Final = 2
MIN_STREAK: Final = 2
MONTH_WINDOW: Final = timedelta(days=30)


@dataclass(frozen=True, slots=True)
class ChatTotals:
    games: int
    civilian_wins: int
    spy_wins: int


@dataclass(frozen=True, slots=True)
class Champion:
    name: str
    value: int
    total: int | None = None


@dataclass(frozen=True, slots=True)
class HallOfFame:
    totals: ChatTotals
    spy_of_the_month: Champion | None = None
    best_detective: Champion | None = None
    first_victim: Champion | None = None
    longest_streak: Champion | None = None

    @property
    def has_titles(self) -> bool:
        return any(
            title is not None
            for title in (
                self.spy_of_the_month,
                self.best_detective,
                self.first_victim,
                self.longest_streak,
            )
        )


@dataclass(frozen=True, slots=True)
class PlayerProfile:
    games: int
    wins: int
    spy_games: int
    spy_wins: int
    streak: int
    first_outs: int

    @property
    def civilian_games(self) -> int:
        return self.games - self.spy_games

    @property
    def civilian_wins(self) -> int:
        return self.wins - self.spy_wins

    @property
    def win_rate(self) -> int:
        return round(100 * self.wins / self.games) if self.games else 0


class StatsSource(Protocol):
    async def chat_totals(self, chat_id: int) -> ChatTotals: ...

    async def hall_of_fame(self, chat_id: int, now: datetime) -> HallOfFame: ...

    async def player_profile(self, chat_id: int, user_id: int) -> PlayerProfile | None: ...


StatsSourceFactory = Callable[[], AbstractAsyncContextManager[StatsSource]]
