import logging
from collections.abc import Sequence
from typing import Final

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from undercover.bot.lobby_view import LobbyAction, LobbyCB, join_link, render_lobby
from undercover.bot.message_utils import show_or_resend_text
from undercover.bot.role_delivery import deliver_roles
from undercover.bot.routers.reveal import PhaseStarter
from undercover.game.engine import (
    CatalogFactory,
    CategoryRecord,
    EmptyWordCatalogError,
    GameRulesError,
    create_session,
)
from undercover.game.lobby import (
    cycle_spies_count,
    cycle_turn_seconds,
    ensure_playable,
    join,
    leave,
    toggle_category,
    unique_name,
)
from undercover.game.models import GameMode, LobbyPlayer, LobbyState, LobbyView
from undercover.redis.game_state import GameStateRepository
from undercover.redis.lobby_state import LobbyRepository
from undercover.texts import GAME_COMMAND, Errors, Lobby, empty_catalog_text
from undercover.utils.secure_random import secure_rng

logger = logging.getLogger(__name__)

GROUP_CHATS: Final = frozenset({"group", "supergroup"})


def create_lobby_router(open_catalog: CatalogFactory, start_discussion: PhaseStarter) -> Router:
    router = Router(name="lobby")

    async def redraw(bot: Bot, lobbies: LobbyRepository, lobby: LobbyState) -> None:
        await render_lobby(bot, lobbies, lobby, await _categories(open_catalog))

    @router.message(Command(GAME_COMMAND), F.chat.type.in_(GROUP_CHATS))
    async def cmd_game(
        message: Message, bot: Bot, games: GameStateRepository, lobbies: LobbyRepository
    ) -> None:
        if message.from_user is None:
            return
        if await games.load_active(message.chat.id) is not None:
            await message.answer(Errors.GAME_IN_CHAT)
            return

        lobby = await lobbies.load(message.chat.id) or LobbyState(
            chat_id=message.chat.id, host_user_id=message.from_user.id
        )
        lobby.message_id = None
        await redraw(bot, lobbies, lobby)

    @router.message(Command(GAME_COMMAND))
    async def cmd_game_elsewhere(message: Message) -> None:
        await message.answer(Errors.GROUP_ONLY)

    @router.callback_query(LobbyCB.filter(F.action == LobbyAction.JOIN))
    async def cb_join(callback: CallbackQuery, bot: Bot, lobbies: LobbyRepository) -> None:
        lobby = await _open_lobby(callback, lobbies)
        if lobby is None:
            return
        if lobby.index_of(callback.from_user.id) is not None:
            await callback.answer(Lobby.ALREADY_IN, show_alert=True)
            return
        if not await _ping_direct_chat(bot, callback, lobby.chat_id):
            return

        player = LobbyPlayer(
            user_id=callback.from_user.id,
            name=unique_name(
                callback.from_user.full_name, [member.name for member in lobby.players]
            ),
        )
        try:
            join(lobby, player)
        except GameRulesError as error:
            await callback.answer(str(error), show_alert=True)
            return

        await redraw(bot, lobbies, lobby)
        await callback.answer()

    @router.callback_query(LobbyCB.filter(F.action == LobbyAction.LEAVE))
    async def cb_leave(callback: CallbackQuery, bot: Bot, lobbies: LobbyRepository) -> None:
        lobby = await _open_lobby(callback, lobbies)
        if lobby is None:
            return
        try:
            leave(lobby, callback.from_user.id)
        except GameRulesError:
            await callback.answer(Lobby.NOT_IN, show_alert=True)
            return

        await redraw(bot, lobbies, lobby)
        await callback.answer()

    @router.callback_query(LobbyCB.filter(F.action == LobbyAction.SPIES))
    async def cb_spies(callback: CallbackQuery, bot: Bot, lobbies: LobbyRepository) -> None:
        lobby = await _host_lobby(callback, lobbies)
        if lobby is None:
            return
        cycle_spies_count(lobby)
        await redraw(bot, lobbies, lobby)
        await callback.answer()

    @router.callback_query(LobbyCB.filter(F.action == LobbyAction.TURN))
    async def cb_turn_seconds(callback: CallbackQuery, bot: Bot, lobbies: LobbyRepository) -> None:
        lobby = await _host_lobby(callback, lobbies)
        if lobby is None:
            return
        cycle_turn_seconds(lobby)
        await redraw(bot, lobbies, lobby)
        await callback.answer()

    @router.callback_query(LobbyCB.filter(F.action == LobbyAction.CATEGORIES))
    async def cb_categories(callback: CallbackQuery, bot: Bot, lobbies: LobbyRepository) -> None:
        lobby = await _host_lobby(callback, lobbies)
        if lobby is None:
            return
        lobby.view = LobbyView.CATEGORIES
        await redraw(bot, lobbies, lobby)
        await callback.answer()

    @router.callback_query(LobbyCB.filter(F.action == LobbyAction.CATEGORY))
    async def cb_category(
        callback: CallbackQuery,
        callback_data: LobbyCB,
        bot: Bot,
        lobbies: LobbyRepository,
    ) -> None:
        lobby = await _host_lobby(callback, lobbies)
        if lobby is None:
            return
        toggle_category(lobby, callback_data.value)
        await redraw(bot, lobbies, lobby)
        await callback.answer()

    @router.callback_query(LobbyCB.filter(F.action == LobbyAction.DONE))
    async def cb_categories_done(
        callback: CallbackQuery, bot: Bot, lobbies: LobbyRepository
    ) -> None:
        lobby = await _host_lobby(callback, lobbies)
        if lobby is None:
            return
        lobby.view = LobbyView.ROSTER
        await redraw(bot, lobbies, lobby)
        await callback.answer()

    @router.callback_query(LobbyCB.filter(F.action == LobbyAction.PLAY))
    async def cb_play(
        callback: CallbackQuery,
        bot: Bot,
        games: GameStateRepository,
        lobbies: LobbyRepository,
    ) -> None:
        lobby = await _host_lobby(callback, lobbies)
        if lobby is None:
            return
        if await games.load_active(lobby.chat_id) is not None:
            await callback.answer(Errors.GAME_IN_CHAT, show_alert=True)
            return
        try:
            ensure_playable(lobby)
        except GameRulesError as error:
            await callback.answer(str(error), show_alert=True)
            return

        try:
            async with open_catalog() as words:
                state = await create_session(
                    chat_id=lobby.chat_id,
                    host_user_id=lobby.host_user_id,
                    player_names=[player.name for player in lobby.players],
                    player_ids=[player.user_id for player in lobby.players],
                    spies_count=lobby.spies_count,
                    words=words,
                    rng=secure_rng(),
                    category_ids=lobby.category_ids,
                    mode=GameMode.GROUP,
                    turn_seconds=lobby.turn_seconds,
                )
        except EmptyWordCatalogError:
            logger.exception("чат %s: партию не собрать, словарь пуст", lobby.chat_id)
            await callback.answer(empty_catalog_text(lobby.category_ids), show_alert=True)
            return

        undelivered = await deliver_roles(bot, state)
        if undelivered:
            await callback.answer(Lobby.DELIVERY_FAILED, show_alert=True)
            await bot.send_message(
                lobby.chat_id,
                Lobby.OPEN_DM.format(names=", ".join(player.name for player in undelivered))
                + f"\n{await join_link(bot, lobby.chat_id)}",
            )
            return

        await games.save(state)
        await lobbies.delete(lobby.chat_id)
        await show_or_resend_text(bot, lobby.chat_id, lobby.message_id, Lobby.STARTED)
        await start_discussion(bot, games, state)
        await callback.answer()

    return router


async def _categories(open_catalog: CatalogFactory) -> Sequence[CategoryRecord]:
    async with open_catalog() as catalog:
        return await catalog.list_playable_categories()


async def _open_lobby(callback: CallbackQuery, lobbies: LobbyRepository) -> LobbyState | None:
    lobby = None if callback.message is None else await lobbies.load(callback.message.chat.id)
    if lobby is None:
        await callback.answer(Errors.LOBBY_CLOSED, show_alert=True)
    return lobby


async def _host_lobby(callback: CallbackQuery, lobbies: LobbyRepository) -> LobbyState | None:
    lobby = await _open_lobby(callback, lobbies)
    if lobby is None:
        return None
    if callback.from_user.id != lobby.host_user_id:
        await callback.answer(Errors.NOT_HOST, show_alert=True)
        return None
    return lobby


async def _ping_direct_chat(bot: Bot, callback: CallbackQuery, chat_id: int) -> bool:
    try:
        await bot.send_message(callback.from_user.id, Lobby.DM_WELCOME)
    except TelegramForbiddenError:
        await callback.answer(url=await join_link(bot, chat_id))
        return False
    return True
