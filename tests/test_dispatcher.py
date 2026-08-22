from typing import Final

import pytest
from aiogram import Bot, Dispatcher
from aiogram.dispatcher.event.telegram import TelegramEventObserver
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.methods import SetMyCommands
from aiogram.types import BotCommandScopeAllGroupChats

from conftest import settings_for
from fake_bot import FakeSession, make_bot
from undercover.bot.dispatcher import (
    create_bot,
    create_dispatcher,
    resolve_allowed_updates,
)
from undercover.bot.middlewares.throttling import ThrottlingMiddleware
from undercover.bot.turn_clock import TurnClock
from undercover.di import AppDependencies, build_dependencies

EXPECTED_ROUTERS: Final = (
    "start",
    "lobby",
    "Setup",
    "reveal",
    "discussion",
    "finale",
    "errors",
)


@pytest.fixture
def dependencies() -> AppDependencies:
    return build_dependencies(settings_for())


@pytest.fixture
def dispatcher(dependencies: AppDependencies) -> Dispatcher:
    return create_dispatcher(dependencies)


def test_every_phase_of_the_game_is_registered(dispatcher: Dispatcher) -> None:
    names = [router.name for router in dispatcher.sub_routers]

    assert names[: len(EXPECTED_ROUTERS)] == list(EXPECTED_ROUTERS)


def test_errors_are_caught_after_everything_else(dispatcher: Dispatcher) -> None:
    names = [router.name for router in dispatcher.sub_routers]

    assert names.index("errors") > names.index("discussion")


def test_handlers_get_their_dependencies(
    dispatcher: Dispatcher, dependencies: AppDependencies
) -> None:
    assert dispatcher.workflow_data["games"] is dependencies.games
    assert dispatcher.workflow_data["sessionmaker"] is dependencies.sessionmaker
    assert "engine" not in dispatcher.workflow_data


def test_throttling_guards_both_messages_and_presses(dispatcher: Dispatcher) -> None:
    def throttlers(observer: TelegramEventObserver) -> list[object]:
        return [
            middleware
            for middleware in observer.outer_middleware
            if isinstance(middleware, ThrottlingMiddleware)
        ]

    on_messages = throttlers(dispatcher.message)
    on_presses = throttlers(dispatcher.callback_query)

    assert len(on_messages) == len(on_presses) == 1

    assert on_messages[0] is on_presses[0]


def test_the_fsm_lives_in_redis_with_dialog_keys(
    dispatcher: Dispatcher, dependencies: AppDependencies
) -> None:
    storage = dispatcher.storage

    assert isinstance(storage, RedisStorage)
    assert isinstance(storage.key_builder, DefaultKeyBuilder)
    assert storage.key_builder.with_destiny is True


def test_only_real_telegram_updates_are_requested(dispatcher: Dispatcher) -> None:
    allowed = resolve_allowed_updates(dispatcher)

    assert "message" in allowed
    assert "callback_query" in allowed
    assert "aiogd_update" not in allowed


def test_names_from_the_table_are_never_parsed_as_markup() -> None:
    bot = create_bot(settings_for())

    assert bot.default.parse_mode is None


async def test_the_command_menu_is_published_on_startup(dispatcher: Dispatcher) -> None:
    session = FakeSession()
    bot = make_bot(session)

    await dispatcher.emit_startup(bot=bot)

    published = session.calls(SetMyCommands)
    assert [command.command for command in published[0].commands] == ["start"]


async def test_group_chats_see_the_game_command_in_the_menu(dispatcher: Dispatcher) -> None:
    session = FakeSession()

    await dispatcher.emit_startup(bot=make_bot(session))

    group_menus = [
        call
        for call in session.calls(SetMyCommands)
        if isinstance(call.scope, BotCommandScopeAllGroupChats)
    ]
    assert [[command.command for command in call.commands] for call in group_menus] == [
        ["start", "undercover"]
    ]


async def test_private_chats_are_not_offered_a_group_only_command(
    dispatcher: Dispatcher,
) -> None:
    session = FakeSession()

    await dispatcher.emit_startup(bot=make_bot(session))

    default_menus = [call for call in session.calls(SetMyCommands) if call.scope is None]
    assert all(
        "undercover" not in [command.command for command in call.commands] for call in default_menus
    )


async def test_a_telegram_outage_does_not_stop_the_start(
    dispatcher: Dispatcher, capsys: pytest.CaptureFixture[str]
) -> None:
    session = FakeSession()
    session.failures[SetMyCommands] = RuntimeError("Telegram недоступен")

    await dispatcher.emit_startup(bot=make_bot(session))

    assert "Traceback" not in capsys.readouterr().err


def test_the_bot_carries_the_configured_token() -> None:
    settings = settings_for()

    bot: Bot = create_bot(settings)

    assert bot.token == settings.bot_token.get_secret_value()


def test_the_turn_clock_stops_with_the_bot(dispatcher: Dispatcher) -> None:
    owners = [
        getattr(handler.callback, "__self__", None) for handler in dispatcher.shutdown.handlers
    ]

    assert any(isinstance(owner, TurnClock) for owner in owners)
