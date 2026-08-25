from collections.abc import Callable, Mapping
from typing import Final

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from undercover.bot.acks import ack
from undercover.bot.callbacks import LobbyAction, LobbyCB
from undercover.bot.deep_links import join_link, rules_link
from undercover.bot.filters import IN_GROUP
from undercover.bot.lobby_view import render_lobby
from undercover.bot.message_utils import show_or_resend_text
from undercover.bot.phases import PhaseStarter
from undercover.bot.role_delivery import deliver_roles
from undercover.game.catalog import CachedCatalog
from undercover.game.engine import EmptyWordCatalogError, create_session, secure_rng
from undercover.game.lobby import ensure_playable, leave, seat
from undercover.game.models import LobbyState, LobbyView, Seating
from undercover.game.rules import GameRulesError
from undercover.game.settings import (
    cycle_spies,
    cycle_turn_seconds,
    toggle_category,
    toggle_ruleset,
)
from undercover.log import get_logger
from undercover.redis.game_state import GameStateRepository
from undercover.redis.lobby_state import LobbyRepository
from undercover.texts import GAME_COMMAND, RULE_REFUSALS, Errors, Lobby, Rules, empty_catalog_text

logger = get_logger(__name__)


LobbyMutator = Callable[[LobbyState, int], None]


def _set_view(view: LobbyView) -> LobbyMutator:
    def apply(lobby: LobbyState, _value: int) -> None:
        lobby.view = view

    return apply


LOBBY_MUTATORS: Final[Mapping[LobbyAction, LobbyMutator]] = {
    LobbyAction.SPIES: lambda lobby, _value: cycle_spies(lobby.settings, len(lobby.players)),
    LobbyAction.TURN: lambda lobby, _value: cycle_turn_seconds(lobby.settings),
    LobbyAction.RULESET: lambda lobby, _value: toggle_ruleset(lobby.settings),
    LobbyAction.CATEGORY: lambda lobby, value: toggle_category(lobby.settings, value),
    LobbyAction.CATEGORIES: _set_view(LobbyView.CATEGORIES),
    LobbyAction.DONE: _set_view(LobbyView.ROSTER),
}


def create_lobby_router(catalog: CachedCatalog, start_discussion: PhaseStarter) -> Router:
    router = Router(name="lobby")

    async def redraw(bot: Bot, lobbies: LobbyRepository, lobby: LobbyState) -> None:
        await render_lobby(bot, lobbies, lobby, await catalog.categories())

    @router.message(Command(GAME_COMMAND), IN_GROUP)
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
            await ack(callback, Lobby.ALREADY_IN, show_alert=True)
            return
        if not await _ping_direct_chat(bot, callback, lobby.chat_id):
            return

        try:
            seat(lobby, callback.from_user.id, callback.from_user.full_name)
        except GameRulesError as error:
            await ack(callback, RULE_REFUSALS[error.rule], show_alert=True)
            return

        await redraw(bot, lobbies, lobby)
        await ack(callback)

    @router.callback_query(LobbyCB.filter(F.action == LobbyAction.LEAVE))
    async def cb_leave(callback: CallbackQuery, bot: Bot, lobbies: LobbyRepository) -> None:
        lobby = await _open_lobby(callback, lobbies)
        if lobby is None:
            return
        try:
            leave(lobby, callback.from_user.id)
        except GameRulesError:
            await ack(callback, Lobby.NOT_IN, show_alert=True)
            return

        await redraw(bot, lobbies, lobby)
        await ack(callback)

    @router.callback_query(LobbyCB.filter(F.action == LobbyAction.RULES))
    async def cb_rules(callback: CallbackQuery, bot: Bot) -> None:
        try:
            await bot.send_message(callback.from_user.id, Rules.FULL)
        except TelegramForbiddenError:
            await ack(callback, url=await rules_link(bot))
            return
        await ack(callback, Lobby.RULES_SENT)

    @router.callback_query(LobbyCB.filter(F.action.in_(set(LOBBY_MUTATORS))))
    async def cb_settings(
        callback: CallbackQuery,
        callback_data: LobbyCB,
        bot: Bot,
        lobbies: LobbyRepository,
    ) -> None:
        lobby = await _host_lobby(callback, lobbies)
        if lobby is None:
            return
        LOBBY_MUTATORS[callback_data.action](lobby, callback_data.value)
        await redraw(bot, lobbies, lobby)
        await ack(callback)

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
            logger.info("lobby.play_refused", chat_id=lobby.chat_id, reason="партия уже идёт")
            await ack(callback, Errors.GAME_IN_CHAT, show_alert=True)
            return
        try:
            ensure_playable(lobby)
        except GameRulesError as error:
            logger.info("lobby.play_refused", chat_id=lobby.chat_id, reason=error.rule.value)
            await ack(callback, RULE_REFUSALS[error.rule], show_alert=True)
            return

        await ack(callback)
        logger.info(
            "lobby.play_requested",
            chat_id=lobby.chat_id,
            players=len(lobby.players),
            spies=lobby.settings.spies_count,
            ruleset=lobby.settings.ruleset.value,
            turn_seconds=lobby.settings.turn_seconds,
            categories=sorted(lobby.settings.category_ids),
        )

        try:
            async with catalog.open() as words:
                state = await create_session(
                    chat_id=lobby.chat_id,
                    host_user_id=lobby.host_user_id,
                    player_names=[player.name for player in lobby.players],
                    player_ids=[player.user_id for player in lobby.players],
                    spies_count=lobby.settings.spies_count,
                    words=words,
                    rng=secure_rng(),
                    category_ids=lobby.settings.category_ids,
                    seating=Seating.GROUP,
                    ruleset=lobby.settings.ruleset,
                    turn_seconds=lobby.settings.turn_seconds,
                )
        except EmptyWordCatalogError:
            logger.warning(
                "lobby.empty_catalog",
                chat_id=lobby.chat_id,
                categories=sorted(lobby.settings.category_ids),
            )
            await bot.send_message(lobby.chat_id, empty_catalog_text(lobby.settings.category_ids))
            return

        undelivered = await deliver_roles(bot, state)
        if undelivered:
            logger.warning(
                "lobby.play_aborted",
                chat_id=lobby.chat_id,
                session_id=state.session_id,
                reason="роли дошли не всем",
                undelivered=[player.name for player in undelivered],
            )
            await bot.send_message(
                lobby.chat_id,
                Lobby.DELIVERY_FAILED
                + "\n"
                + Lobby.OPEN_DM.format(names=", ".join(player.name for player in undelivered))
                + f"\n{await join_link(bot, lobby.chat_id)}",
            )
            return

        await games.save(state)
        await lobbies.delete(lobby.chat_id)
        await show_or_resend_text(bot, lobby.chat_id, lobby.message_id, Lobby.STARTED)
        logger.info(
            "game.started",
            chat_id=lobby.chat_id,
            session_id=state.session_id,
            players=len(state.players),
            spies=sum(player.is_spy for player in state.players),
        )
        await start_discussion(bot, games, state)

    return router


async def _open_lobby(callback: CallbackQuery, lobbies: LobbyRepository) -> LobbyState | None:
    lobby = None if callback.message is None else await lobbies.load(callback.message.chat.id)
    if lobby is None:
        await ack(callback, Errors.LOBBY_CLOSED, show_alert=True)
    return lobby


async def _host_lobby(callback: CallbackQuery, lobbies: LobbyRepository) -> LobbyState | None:
    lobby = await _open_lobby(callback, lobbies)
    if lobby is None:
        return None
    if callback.from_user.id != lobby.host_user_id:
        await ack(callback, Errors.NOT_HOST, show_alert=True)
        return None
    return lobby


async def _ping_direct_chat(bot: Bot, callback: CallbackQuery, chat_id: int) -> bool:
    try:
        await bot.send_message(callback.from_user.id, Lobby.DM_WELCOME)
    except TelegramForbiddenError:
        await ack(callback, url=await join_link(bot, chat_id))
        return False
    return True
