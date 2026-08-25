from typing import Final

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from undercover.log import get_logger

logger = get_logger(__name__)

SCRIPT_LOCATION: Final = "undercover.db:migrations"

HEAD: Final = "head"


class SchemaUpgradeError(RuntimeError):
    pass


async def upgrade_to_head(engine: AsyncEngine) -> None:
    logger.info("schema.upgrade_started", revision=HEAD)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(_upgrade)
    except Exception as error:
        logger.warning(
            "schema.upgrade_failed", revision=HEAD, error=type(error).__name__, reason=str(error)
        )
        raise SchemaUpgradeError(f"{type(error).__name__}: {error}") from error
    logger.info("schema.upgrade_done", revision=HEAD)


def _upgrade(connection: Connection) -> None:
    config = Config(attributes={"connection": connection})
    config.set_main_option("script_location", SCRIPT_LOCATION)
    command.upgrade(config, HEAD)
