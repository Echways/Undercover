import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from undercover.bot.message_utils import as_photo
from undercover.game.models import GameSessionState, PlayerState
from undercover.media.card_renderer import (
    CARD_SUFFIX,
    render_civilian_card,
    render_spy_card,
)
from undercover.texts import Delivery

logger = logging.getLogger(__name__)


def render_role_card(player: PlayerState, state: GameSessionState) -> bytes:
    if player.is_spy:
        return render_spy_card(player.name, state.hint_by_spy[player.order_index])
    return render_civilian_card(player.name, state.word_text)


async def deliver_roles(bot: Bot, state: GameSessionState) -> list[PlayerState]:
    delivered = await asyncio.gather(
        *(_deliver_one(bot, state, player) for player in state.players)
    )
    return [player for player, reached in zip(state.players, delivered, strict=True) if not reached]


async def _deliver_one(bot: Bot, state: GameSessionState, player: PlayerState) -> bool:
    if player.user_id is None:
        logger.warning("партия %s: у игрока %s нет личного чата", state.session_id, player.name)
        return False

    try:
        image = await asyncio.to_thread(render_role_card, player, state)
        await bot.send_photo(
            player.user_id,
            as_photo(image, f"role_{player.order_index}.{CARD_SUFFIX}"),
            caption=Delivery.ROLE_CAPTION,
        )
    except TelegramAPIError as error:
        logger.info("партия %s: роль не дошла до %s (%s)", state.session_id, player.name, error)
        return False
    return True
