import logging
from typing import Final

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

SCRIPT_LOCATION: Final = "undercover.db:migrations"

HEAD: Final = "head"


class SchemaUpgradeError(RuntimeError):
    pass


async def upgrade_to_head(engine: AsyncEngine) -> None:
    try:
        async with engine.begin() as connection:
            await connection.run_sync(_upgrade)
    except Exception as error:
        raise SchemaUpgradeError(f"{type(error).__name__}: {error}") from error
    logger.info("схема базы приведена к последней ревизии")


def _upgrade(connection: Connection) -> None:
    config = Config(attributes={"connection": connection})
    config.set_main_option("script_location", SCRIPT_LOCATION)
    command.upgrade(config, HEAD)
