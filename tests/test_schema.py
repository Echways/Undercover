import tomllib
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from conftest import REPO_ROOT, run_alembic, settings_for
from undercover.db.schema import SCRIPT_LOCATION, SchemaUpgradeError, upgrade_to_head

FIRST_REVISION = "4b1a63a34ad9"


def head_revision() -> str:
    config = Config()
    config.set_main_option("script_location", SCRIPT_LOCATION)
    found = ScriptDirectory.from_config(config).get_current_head()
    assert found is not None
    return found


async def revision_of(engine: AsyncEngine) -> str | None:
    async with engine.connect() as connection:
        tables = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
        if "alembic_version" not in tables:
            return None
        found = await connection.execute(text("SELECT version_num FROM alembic_version"))
        stamped = found.scalar_one_or_none()
        return None if stamped is None else str(stamped)


async def columns_of(engine: AsyncEngine, table: str) -> set[str]:
    async with engine.connect() as connection:
        described = await connection.run_sync(lambda sync: inspect(sync).get_columns(table))
        return {column["name"] for column in described}


def test_the_runner_and_the_cli_read_the_same_migrations() -> None:
    with (REPO_ROOT / "pyproject.toml").open("rb") as manifest:
        configured = tomllib.load(manifest)["tool"]["alembic"]["script_location"]

    assert configured == SCRIPT_LOCATION


def test_the_migrations_live_where_the_runner_looks() -> None:
    package, _, folder = SCRIPT_LOCATION.partition(":")

    assert (REPO_ROOT / "src" / Path(*package.split(".")) / folder / "env.py").is_file()


async def test_an_unreachable_database_is_reported_as_a_schema_failure() -> None:
    engine = create_async_engine(
        settings_for(POSTGRES_HOST="127.0.0.1", POSTGRES_PORT="1").postgres_dsn
    )
    try:
        with pytest.raises(SchemaUpgradeError):
            await upgrade_to_head(engine)
    finally:
        await engine.dispose()


class TestOnPostgres:
    pytestmark = pytest.mark.integration

    @pytest.fixture
    async def bare(self, postgres_env: dict[str, str]) -> AsyncIterator[AsyncEngine]:
        assert run_alembic(postgres_env, "downgrade", "base").returncode == 0
        engine = create_async_engine(settings_for(**postgres_env).postgres_dsn)
        try:
            yield engine
        finally:
            await engine.dispose()
            assert run_alembic(postgres_env, "upgrade", "head").returncode == 0

    async def test_an_empty_database_is_brought_up_to_head(self, bare: AsyncEngine) -> None:
        assert await revision_of(bare) is None

        await upgrade_to_head(bare)

        assert await revision_of(bare) == head_revision()

    async def test_a_database_left_behind_catches_up(
        self, bare: AsyncEngine, postgres_env: dict[str, str]
    ) -> None:
        assert run_alembic(postgres_env, "upgrade", FIRST_REVISION).returncode == 0
        assert "winner" not in await columns_of(bare, "game_sessions_log")

        await upgrade_to_head(bare)

        assert "winner" in await columns_of(bare, "game_sessions_log")
        assert "game_player_results" in await _tables(bare)

    async def test_a_database_already_at_head_is_left_alone(self, bare: AsyncEngine) -> None:
        await upgrade_to_head(bare)

        await upgrade_to_head(bare)

        assert await revision_of(bare) == head_revision()


async def _tables(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as connection:
        return set(await connection.run_sync(lambda sync: inspect(sync).get_table_names()))
