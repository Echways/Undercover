import asyncio
from time import monotonic

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from undercover.bot.message_utils import as_photo
from undercover.game.models import GameSessionState, PlayerState
from undercover.log import get_logger
from undercover.media.card_renderer import (
    CARD_SUFFIX,
    render_civilian_card,
    render_spy_card,
)
from undercover.texts import Delivery

logger = get_logger(__name__)


def render_role_card(player: PlayerState, state: GameSessionState) -> bytes:
    if player.is_spy:
        return render_spy_card(player.name, state.hint_by_spy[player.order_index])
    return render_civilian_card(player.name, state.word_text)


async def deliver_roles(bot: Bot, state: GameSessionState) -> list[PlayerState]:
    logger.info("roles.delivering", session_id=state.session_id, players=len(state.players))
    started = monotonic()

    delivered = await asyncio.gather(
        *(_deliver_one(bot, state, player) for player in state.players)
    )
    undelivered = [
        player for player, reached in zip(state.players, delivered, strict=True) if not reached
    ]

    logger.info(
        "roles.delivered",
        session_id=state.session_id,
        reached=len(state.players) - len(undelivered),
        undelivered=[player.name for player in undelivered],
        duration_ms=_elapsed_ms(started),
    )
    return undelivered


async def _deliver_one(bot: Bot, state: GameSessionState, player: PlayerState) -> bool:
    if player.user_id is None:
        logger.warning(
            "roles.no_direct_chat",
            session_id=state.session_id,
            player=player.name,
            order_index=player.order_index,
        )
        return False

    started = monotonic()
    image = await asyncio.to_thread(render_role_card, player, state)
    logger.debug(
        "roles.card_rendered",
        session_id=state.session_id,
        player=player.name,
        bytes=len(image),
        duration_ms=_elapsed_ms(started),
    )

    try:
        await bot.send_photo(
            player.user_id,
            as_photo(image, f"role_{player.order_index}.{CARD_SUFFIX}"),
            caption=Delivery.ROLE_CAPTION,
        )
    except TelegramAPIError as error:
        logger.warning(
            "roles.rejected",
            session_id=state.session_id,
            player=player.name,
            user_id=player.user_id,
            error=type(error).__name__,
            reason=str(error),
        )
        return False

    logger.debug(
        "roles.sent",
        session_id=state.session_id,
        player=player.name,
        user_id=player.user_id,
        duration_ms=_elapsed_ms(started),
    )
    return True


def _elapsed_ms(started: float) -> int:
    return round((monotonic() - started) * 1000)
