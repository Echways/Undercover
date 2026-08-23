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
from undercover.log import DEFAULT_LEVEL, configure_logging

logger = logging.getLogger(__name__)

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
        logger.error("Запуск невозможен: %s", _reason(error))
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        logger.info("Остановлено вручную")


async def _run() -> None:
    settings = load_settings()
    logging.getLogger().setLevel(settings.log_level)

    dependencies = build_dependencies(settings)
    bot = create_bot(settings)
    try:
        await dependencies.check_connections()
        await upgrade_to_head(dependencies.engine)
        dispatcher = create_dispatcher(dependencies)
        logger.info("Undercover: запускаем опрос Telegram")
        await dispatcher.start_polling(
            bot,
            allowed_updates=resolve_allowed_updates(dispatcher),
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
