import re
from typing import Final

from aiogram import Bot, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message
from aiogram_dialog import DialogManager, StartMode

from undercover.bot.lobby_view import JOIN_PAYLOAD_PREFIX, render_lobby
from undercover.bot.routers.setup_draft import Setup
from undercover.game.catalog import CachedCatalog
from undercover.game.engine import GameRulesError
from undercover.game.lobby import seat
from undercover.redis.lobby_state import LobbyRepository
from undercover.texts import Errors, Lobby, Start

JOIN_PAYLOAD: Final = re.compile(rf"^{JOIN_PAYLOAD_PREFIX}(-?\d+)$")


def create_start_router(catalog: CachedCatalog) -> Router:
    router = Router(name="start")

    @router.message(CommandStart(deep_link=True, magic=F.args.regexp(JOIN_PAYLOAD)))
    async def cmd_join_lobby(
        message: Message,
        command: CommandObject,
        bot: Bot,
        lobbies: LobbyRepository,
    ) -> None:
        payload = JOIN_PAYLOAD.match(command.args or "")
        if payload is None or message.from_user is None:
            return

        lobby = await lobbies.load(int(payload.group(1)))
        if lobby is None:
            await message.answer(Errors.LOBBY_CLOSED)
            return
        if lobby.index_of(message.from_user.id) is not None:
            await message.answer(Lobby.ALREADY_IN)
            return

        try:
            seat(lobby, message.from_user.id, message.from_user.full_name)
        except GameRulesError as error:
            await message.answer(str(error))
            return

        await message.answer(Lobby.DM_WELCOME)
        await render_lobby(bot, lobbies, lobby, await catalog.categories())

    @router.message(CommandStart())
    async def cmd_start(message: Message, dialog_manager: DialogManager) -> None:
        await message.answer(Start.GREETING)
        await dialog_manager.start(Setup.ask_players_count, mode=StartMode.RESET_STACK)

    return router
