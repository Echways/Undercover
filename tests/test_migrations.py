import pytest
from sqlalchemy import inspect
from sqlalchemy.engine.interfaces import ReflectedForeignKeyConstraint
from sqlalchemy.ext.asyncio import create_async_engine

from conftest import run_alembic

pytestmark = pytest.mark.integration

DOMAIN_TABLES = {"categories", "words", "spy_hints", "game_sessions_log", "game_player_results"}


async def _table_names(dsn: str) -> set[str]:
    engine = create_async_engine(dsn)
    try:
        async with engine.connect() as connection:
            return set(await connection.run_sync(lambda sync: inspect(sync).get_table_names()))
    finally:
        await engine.dispose()


async def test_upgrade_creates_domain_tables(migrated_dsn: str) -> None:
    assert await _table_names(migrated_dsn) >= DOMAIN_TABLES


async def test_models_match_migrations(postgres_env: dict[str, str], migrated_dsn: str) -> None:
    completed = run_alembic(postgres_env, "check")

    assert completed.returncode == 0, completed.stdout + completed.stderr


async def test_downgrade_removes_domain_tables(
    postgres_env: dict[str, str], migrated_dsn: str
) -> None:
    assert run_alembic(postgres_env, "downgrade", "base").returncode == 0
    try:
        assert not DOMAIN_TABLES & await _table_names(migrated_dsn)
    finally:
        assert run_alembic(postgres_env, "upgrade", "head").returncode == 0


async def _columns(dsn: str, table: str) -> set[str]:
    engine = create_async_engine(dsn)
    try:
        async with engine.connect() as connection:
            described = await connection.run_sync(lambda sync: inspect(sync).get_columns(table))
            return {column["name"] for column in described}
    finally:
        await engine.dispose()


async def test_the_journal_has_a_place_for_the_winner(migrated_dsn: str) -> None:
    assert "winner" in await _columns(migrated_dsn, "game_sessions_log")


async def _foreign_keys(dsn: str, table: str) -> list[ReflectedForeignKeyConstraint]:
    engine = create_async_engine(dsn)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(lambda sync: inspect(sync).get_foreign_keys(table))
    finally:
        await engine.dispose()


async def test_a_players_row_dies_with_its_game(migrated_dsn: str) -> None:
    (key,) = [
        found
        for found in await _foreign_keys(migrated_dsn, "game_player_results")
        if found["referred_table"] == "game_sessions_log"
    ]

    assert key["options"]["ondelete"] == "CASCADE"
