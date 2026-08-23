import asyncio
import logging

from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError

from undercover.bot.dispatcher import (
    create_bot,
    create_dispatcher,
    resolve_allowed_updates,
)
from undercover.config import ConfigurationError, load_settings
from undercover.db.schema import SchemaUpgradeError, upgrade_to_head
from undercover.di import DependencyUnavailableError, build_dependencies
from undercover.log import DEFAULT_LEVEL, configure_logging, get_logger

logger = get_logger(__name__)

STARTUP_FAILURES = (
    ConfigurationError,
    DependencyUnavailableError,
    TelegramUnauthorizedError,
    TelegramNetworkError,
    SchemaUpgradeError,
)


def main() -> None:
    configure_logging(DEFAULT_LEVEL)
    try:
        asyncio.run(_run())
    except STARTUP_FAILURES as error:
        logger.error("startup.failed", error=type(error).__name__, reason=_reason(error))
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        logger.info("shutdown.by_hand")


async def _run() -> None:
    settings = load_settings()
    logging.getLogger().setLevel(settings.log_level)

    dependencies = build_dependencies(settings)
    bot = create_bot(settings)
    try:
        await dependencies.check_connections()
        await upgrade_to_head(dependencies.engine)
        dispatcher = create_dispatcher(dependencies)
        allowed = resolve_allowed_updates(dispatcher)
        logger.info("polling.starting", log_level=settings.log_level, allowed_updates=allowed)
        await dispatcher.start_polling(
            bot,
            allowed_updates=allowed,
            drop_pending_updates=True,
        )
    finally:
        await bot.session.close()
        await dependencies.close()


def _reason(error: Exception) -> str:
    if isinstance(error, TelegramUnauthorizedError):
        return "Telegram отклонил BOT_TOKEN — проверьте токен от @BotFather"
    if isinstance(error, TelegramNetworkError):
        return f"нет связи с Telegram: {error}"
    if isinstance(error, SchemaUpgradeError):
        return f"не удалось обновить схему базы: {error}"
    return str(error)


if __name__ == "__main__":
    main()
