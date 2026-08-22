import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from undercover.config import Settings
from undercover.db.session import check_database_connection, create_engine, create_sessionmaker
from undercover.redis.client import check_redis_connection, create_redis_client
from undercover.redis.game_state import GameStateRepository
from undercover.redis.lobby_state import LobbyRepository

logger = logging.getLogger(__name__)


class DependencyUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AppDependencies:
    settings: Settings
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    redis: Redis
    games: GameStateRepository
    lobbies: LobbyRepository

    def as_workflow_data(self) -> dict[str, Any]:
        return {
            "settings": self.settings,
            "sessionmaker": self.sessionmaker,
            "redis": self.redis,
            "games": self.games,
            "lobbies": self.lobbies,
        }

    async def check_connections(self) -> None:
        await _probe(
            "PostgreSQL",
            self.settings.postgres_target,
            partial(check_database_connection, self.engine),
        )
        await _probe(
            "Redis",
            self.settings.redis_target,
            partial(check_redis_connection, self.redis),
        )

    async def close(self) -> None:
        try:
            await self.redis.aclose()
        finally:
            await self.engine.dispose()


def build_dependencies(settings: Settings) -> AppDependencies:
    engine = create_engine(settings)
    redis = create_redis_client(settings)
    return AppDependencies(
        settings=settings,
        engine=engine,
        sessionmaker=create_sessionmaker(engine),
        redis=redis,
        games=GameStateRepository(redis),
        lobbies=LobbyRepository(redis),
    )


async def _probe(service: str, target: str, check: Callable[[], Awaitable[None]]) -> None:
    try:
        await check()
    except Exception as error:
        raise DependencyUnavailableError(
            f"нет подключения к {service} ({target}): {type(error).__name__}: {error}"
        ) from error
    logger.info("подключение к %s (%s) установлено", service, target)
