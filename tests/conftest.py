import os
import subprocess
import sys
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import docker
import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from undercover.config import Settings
from undercover.redis.client import create_redis_client

ENV_VARS = (
    "BOT_TOKEN",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "REDIS_URL",
    "LOG_LEVEL",
)

VALID_ENV: dict[str, str] = {
    "BOT_TOKEN": "123456789:AA-test-token",
    "POSTGRES_DB": "undercover",
    "POSTGRES_USER": "undercover",
    "POSTGRES_PASSWORD": "s3cret",
    "POSTGRES_HOST": "postgres",
    "POSTGRES_PORT": "5432",
    "REDIS_URL": "redis://redis:6379/0",
}

SetEnv = Callable[..., None]


@pytest.fixture
def set_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> SetEnv:
    monkeypatch.chdir(tmp_path)
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    def _apply(**overrides: str | None) -> None:
        for name, value in {**VALID_ENV, **overrides}.items():
            if value is None:
                monkeypatch.delenv(name, raising=False)
            else:
                monkeypatch.setenv(name, value)

    return _apply


REPO_ROOT = Path(__file__).resolve().parent.parent


def _skip_without_docker() -> None:
    try:
        docker.from_env().ping()
    except Exception as error:
        pytest.skip(f"Docker недоступен, интеграционные тесты пропущены: {error}")


def settings_for(**overrides: str) -> Settings:
    return Settings(**{key.lower(): value for key, value in {**VALID_ENV, **overrides}.items()})


@pytest.fixture(scope="session")
def postgres_env() -> Iterator[dict[str, str]]:
    _skip_without_docker()

    container = PostgresContainer(
        "postgres:16-alpine",
        username="undercover",
        password="p@ss:w/ord",
        dbname="undercover",
        driver=None,
    )
    with container:
        yield {
            **VALID_ENV,
            "POSTGRES_DB": container.dbname,
            "POSTGRES_USER": container.username,
            "POSTGRES_PASSWORD": container.password,
            "POSTGRES_HOST": container.get_container_host_ip(),
            "POSTGRES_PORT": str(container.get_exposed_port(5432)),
        }


def run_alembic(postgres_env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        env={**os.environ, **postgres_env},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="session")
def migrated_dsn(postgres_env: dict[str, str]) -> str:
    completed = run_alembic(postgres_env, "upgrade", "head")
    assert completed.returncode == 0, completed.stderr
    return settings_for(**postgres_env).postgres_dsn


@pytest.fixture
async def db_session(migrated_dsn: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_dsn)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()

            session = AsyncSession(
                bind=connection,
                join_transaction_mode="create_savepoint",
                expire_on_commit=False,
            )
            try:
                yield session
            finally:
                await session.close()
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    _skip_without_docker()
    with RedisContainer("redis:7-alpine") as container:
        host = container.get_container_host_ip()
        yield f"redis://{host}:{container.get_exposed_port(6379)}/0"


@pytest.fixture
async def redis_client(redis_url: str) -> AsyncIterator[Redis]:
    client = create_redis_client(settings_for(REDIS_URL=redis_url))
    try:
        await client.flushdb()
        yield client
    finally:
        await client.aclose()
