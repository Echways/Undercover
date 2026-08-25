from typing import Final

from aiogram import Bot, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import Chat, Message

from undercover.bot.turn_clock import TurnKeeper
from undercover.game.models import GameSessionState, LobbyState
from undercover.log import get_logger
from undercover.redis.dialog_state import DialogStateRepository
from undercover.redis.game_state import GameStateRepository
from undercover.redis.lobby_state import LobbyRepository
from undercover.texts import RESET_COMMAND, Reset

logger = get_logger(__name__)

CHAT_KEEPERS: Final = frozenset({ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR})

GROUP_TYPES: Final = frozenset({ChatType.GROUP, ChatType.SUPERGROUP})


def create_reset_router(keeper: TurnKeeper) -> Router:
    router = Router(name="reset")

    @router.message(Command(RESET_COMMAND))
    async def cmd_reset(
        message: Message,
        bot: Bot,
        games: GameStateRepository,
        lobbies: LobbyRepository,
        dialogs: DialogStateRepository,
    ) -> None:
        if message.from_user is None:
            return

        game = await games.load_active(message.chat.id)
        lobby = await lobbies.load(message.chat.id)
        stray_dialogs = await dialogs.count(message.chat.id)
        if game is None and lobby is None and not stray_dialogs:
            await message.answer(Reset.NOTHING)
            return
        if not await _may_reset(bot, message.chat, message.from_user.id, game, lobby):
            await message.answer(Reset.DENIED)
            return

        if game is not None:
            keeper.clock.stop(game.session_id)
            await games.delete(game.session_id)
        if lobby is not None:
            await lobbies.delete(message.chat.id)
        await dialogs.clear(message.chat.id)

        logger.info("reset.done", chat_id=message.chat.id, user_id=message.from_user.id)
        await message.answer(Reset.DONE)

    return router


async def _may_reset(
    bot: Bot,
    chat: Chat,
    user_id: int,
    game: GameSessionState | None,
    lobby: LobbyState | None,
) -> bool:
    hosts = {holder.host_user_id for holder in (game, lobby) if holder is not None}
    return user_id in hosts or await _keeps_the_chat(bot, chat, user_id)


async def _keeps_the_chat(bot: Bot, chat: Chat, user_id: int) -> bool:
    if chat.type not in GROUP_TYPES:
        return False
    try:
        member = await bot.get_chat_member(chat.id, user_id)
    except TelegramAPIError as error:
        logger.info("reset.rights_unknown", chat_id=chat.id, user_id=user_id, reason=str(error))
        return False
    return member.status in CHAT_KEEPERS
