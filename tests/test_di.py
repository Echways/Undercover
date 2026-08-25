from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

import pytest
from aiogram import Dispatcher
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from conftest import SetEnv, journal
from undercover.config import Settings, load_settings
from undercover.di import AppDependencies, DependencyUnavailableError, build_dependencies
from undercover.redis.dialog_state import DialogStateRepository
from undercover.redis.game_state import GameStateRepository
from undercover.redis.lobby_state import LobbyRepository


class _StubConnection:
    async def execute(self, statement: object) -> None:
        return None


class _StubEngine:
    def __init__(self, failure: Exception | None = None) -> None:
        self._failure = failure
        self.disposed = False

    @asynccontextmanager
    async def connect(self) -> AsyncGenerator[_StubConnection]:
        if self._failure is not None:
            raise self._failure
        yield _StubConnection()

    async def dispose(self) -> None:
        self.disposed = True


class _StubRedis:
    def __init__(
        self, failure: Exception | None = None, close_failure: Exception | None = None
    ) -> None:
        self._failure = failure
        self._close_failure = close_failure
        self.closed = False

    async def ping(self) -> bool:
        if self._failure is not None:
            raise self._failure
        return True

    async def aclose(self) -> None:
        if self._close_failure is not None:
            raise self._close_failure
        self.closed = True


def _dependencies(
    settings: Settings,
    engine: _StubEngine | None = None,
    redis: _StubRedis | None = None,
) -> AppDependencies:
    return AppDependencies(
        settings=settings,
        engine=cast(AsyncEngine, engine or _StubEngine()),
        sessionmaker=cast("async_sessionmaker[AsyncSession]", object()),
        redis=cast(Redis, redis or _StubRedis()),
        games=cast(GameStateRepository, object()),
        lobbies=cast(LobbyRepository, object()),
        dialogs=cast(DialogStateRepository, object()),
    )


@pytest.fixture
def settings(set_env: SetEnv) -> Settings:
    set_env()
    return load_settings()


def test_build_dependencies_reuses_one_engine(settings: Settings) -> None:
    dependencies = build_dependencies(settings)

    assert dependencies.settings is settings
    assert dependencies.sessionmaker.kw["bind"] is dependencies.engine
    assert dependencies.games._redis is dependencies.redis
    assert dependencies.lobbies._redis is dependencies.redis
    assert dependencies.dialogs._redis is dependencies.redis


def test_workflow_data_reaches_dispatcher(settings: Settings) -> None:
    dependencies = _dependencies(settings)

    dispatcher = Dispatcher(**dependencies.as_workflow_data())

    assert dispatcher["settings"] is settings
    assert dispatcher["redis"] is dependencies.redis
    assert dispatcher["sessionmaker"] is dependencies.sessionmaker
    assert dispatcher["games"] is dependencies.games
    assert dispatcher["lobbies"] is dependencies.lobbies
    assert dispatcher["dialogs"] is dependencies.dialogs


def test_engine_is_not_exposed_to_handlers(settings: Settings) -> None:
    assert set(_dependencies(settings).as_workflow_data()) == {
        "settings",
        "sessionmaker",
        "redis",
        "games",
        "lobbies",
        "dialogs",
    }


async def test_check_connections_logs_both_services(settings: Settings) -> None:
    with journal() as records:
        await _dependencies(settings).check_connections()

    assert [(record["event"], record["service"], record["target"]) for record in records] == [
        ("dependency.ready", "PostgreSQL", "postgres:5432/undercover"),
        ("dependency.ready", "Redis", "redis:6379/0"),
    ]


async def test_unreachable_postgres_is_reported_readably(settings: Settings) -> None:
    dependencies = _dependencies(settings, engine=_StubEngine(OSError("Connection refused")))

    with pytest.raises(DependencyUnavailableError) as error:
        await dependencies.check_connections()

    message = str(error.value)
    assert message == (
        "нет подключения к PostgreSQL (postgres:5432/undercover): OSError: Connection refused"
    )
    assert "s3cret" not in message


async def test_unreachable_redis_is_reported_readably(settings: Settings) -> None:
    dependencies = _dependencies(settings, redis=_StubRedis(OSError("Connection refused")))

    with pytest.raises(DependencyUnavailableError) as error:
        await dependencies.check_connections()

    assert str(error.value) == (
        "нет подключения к Redis (redis:6379/0): OSError: Connection refused"
    )


async def test_close_releases_both_resources(settings: Settings) -> None:
    engine, redis = _StubEngine(), _StubRedis()

    await _dependencies(settings, engine=engine, redis=redis).close()

    assert engine.disposed
    assert redis.closed


async def test_close_disposes_engine_even_if_redis_fails(settings: Settings) -> None:
    engine = _StubEngine()
    redis = _StubRedis(close_failure=OSError("broken pipe"))

    with pytest.raises(OSError):
        await _dependencies(settings, engine=engine, redis=redis).close()

    assert engine.disposed
