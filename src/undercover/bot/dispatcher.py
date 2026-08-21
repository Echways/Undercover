import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import UpdateType
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand
from aiogram_dialog import setup_dialogs

from undercover.bot.errors import create_error_router
from undercover.bot.middlewares.throttling import ThrottlingMiddleware
from undercover.bot.routers.discussion import create_discussion_router, start_discussion
from undercover.bot.routers.reveal import create_reveal_router, start_reveal
from undercover.bot.routers.setup_dialog import create_setup_dialog
from undercover.bot.routers.start import create_start_router
from undercover.config import Settings
from undercover.db.repositories.game_log import game_log_writer
from undercover.db.repositories.words import words_source
from undercover.di import AppDependencies
from undercover.texts import Start

logger = logging.getLogger(__name__)


def create_bot(settings: Settings) -> Bot:
    return Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=None),
    )


def create_dispatcher(dependencies: AppDependencies) -> Dispatcher:
    dispatcher = Dispatcher(
        storage=_create_storage(dependencies),
        **dependencies.as_workflow_data(),
    )

    throttling = ThrottlingMiddleware()
    dispatcher.message.outer_middleware(throttling)
    dispatcher.callback_query.outer_middleware(throttling)

    open_words = words_source(dependencies.sessionmaker)
    log_game = game_log_writer(dependencies.sessionmaker)

    dispatcher.include_router(create_start_router())
    dispatcher.include_router(create_setup_dialog(open_words, start_reveal))
    dispatcher.include_router(create_reveal_router(start_discussion))
    dispatcher.include_router(create_discussion_router(open_words, log_game))
    dispatcher.include_router(create_error_router())

    setup_dialogs(dispatcher)
    dispatcher.startup.register(_publish_commands)
    return dispatcher


def resolve_allowed_updates(dispatcher: Dispatcher) -> list[str]:
    telegram_updates = {update.value for update in UpdateType}
    return sorted(telegram_updates & set(dispatcher.resolve_used_update_types()))


def _create_storage(dependencies: AppDependencies) -> RedisStorage:
    return RedisStorage(
        dependencies.redis,
        key_builder=DefaultKeyBuilder(with_destiny=True),
    )


async def _publish_commands(bot: Bot) -> None:
    try:
        await bot.set_my_commands(
            [BotCommand(command="start", description=Start.COMMAND_DESCRIPTION)]
        )
    except Exception as error:
        logger.warning("не удалось опубликовать меню команд: %s", error)
