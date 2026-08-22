import logging
from functools import partial

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import UpdateType
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand, BotCommandScopeAllGroupChats
from aiogram_dialog import setup_dialogs

from undercover.bot.errors import create_error_router
from undercover.bot.middlewares.throttling import ThrottlingMiddleware
from undercover.bot.routers.discussion import create_discussion_router, start_discussion
from undercover.bot.routers.finale import create_finale_router
from undercover.bot.routers.lobby import create_lobby_router
from undercover.bot.routers.reveal import create_reveal_router, start_reveal
from undercover.bot.routers.setup_dialog import create_setup_dialog
from undercover.bot.routers.start import create_start_router
from undercover.bot.turn_clock import TurnClock, TurnKeeper
from undercover.config import Settings
from undercover.db.repositories.game_log import game_log_writer
from undercover.db.repositories.words import words_source
from undercover.di import AppDependencies
from undercover.texts import GAME_COMMAND, Start
from undercover.utils.keyed_locks import KeyedLocks

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

    keeper = TurnKeeper(clock=TurnClock(), locks=KeyedLocks())
    begin_discussion = partial(start_discussion, keeper=keeper)

    dispatcher.include_router(create_start_router(open_words))
    dispatcher.include_router(create_lobby_router(open_words, begin_discussion))
    dispatcher.include_router(create_setup_dialog(open_words, start_reveal))
    dispatcher.include_router(create_reveal_router(begin_discussion))
    dispatcher.include_router(create_discussion_router(keeper))
    dispatcher.include_router(create_finale_router(open_words, log_game, keeper, begin_discussion))
    dispatcher.include_router(create_error_router())

    setup_dialogs(dispatcher)
    dispatcher.startup.register(_publish_commands)
    dispatcher.shutdown.register(keeper.clock.shutdown)
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
    start = BotCommand(command="start", description=Start.COMMAND_DESCRIPTION)
    game = BotCommand(command=GAME_COMMAND, description=Start.GAME_COMMAND_DESCRIPTION)
    try:
        await bot.set_my_commands([start])
        await bot.set_my_commands([start, game], scope=BotCommandScopeAllGroupChats())
    except Exception as error:
        logger.warning("не удалось опубликовать меню команд: %s", error)
