from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime

from undercover.game.stats import ChatTotals, HallOfFame, PlayerProfile


@dataclass(slots=True)
class FakeStats:
    hall: HallOfFame
    profile: PlayerProfile | None = None
    asked: list[tuple[int, int]] = field(default_factory=list)

    async def chat_totals(self, chat_id: int) -> ChatTotals:
        return self.hall.totals

    async def hall_of_fame(self, chat_id: int, now: datetime) -> HallOfFame:
        return self.hall

    async def player_profile(self, chat_id: int, user_id: int) -> PlayerProfile | None:
        self.asked.append((chat_id, user_id))
        return self.profile

    @asynccontextmanager
    async def open(self) -> AsyncIterator["FakeStats"]:
        yield self
