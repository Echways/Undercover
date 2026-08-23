from datetime import UTC, datetime

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from undercover.bot.filters import IN_GROUP
from undercover.bot.stats_view import (
    StatsAction,
    StatsCB,
    hall_of_fame_keyboard,
    hall_of_fame_text,
    private_text,
    profile_text,
)
from undercover.game.stats import StatsSourceFactory
from undercover.texts import STATS_COMMAND, Errors


def create_stats_router(open_stats: StatsSourceFactory) -> Router:
    router = Router(name="stats")

    async def show_hall(bot: Bot, chat_id: int) -> None:
        async with open_stats() as stats:
            hall = await stats.hall_of_fame(chat_id, datetime.now(UTC))
        await bot.send_message(
            chat_id, hall_of_fame_text(hall), reply_markup=hall_of_fame_keyboard()
        )

    @router.message(Command(STATS_COMMAND), IN_GROUP)
    async def cmd_stats(message: Message, bot: Bot) -> None:
        await show_hall(bot, message.chat.id)

    @router.message(Command(STATS_COMMAND))
    async def cmd_stats_elsewhere(message: Message) -> None:
        async with open_stats() as stats:
            totals = await stats.chat_totals(message.chat.id)
        await message.answer(private_text(totals))

    @router.callback_query(StatsCB.filter(F.action == StatsAction.BOARD))
    async def cb_hall(callback: CallbackQuery, bot: Bot) -> None:
        if callback.message is None:
            await callback.answer(Errors.STALE_BUTTON, show_alert=True)
            return
        await show_hall(bot, callback.message.chat.id)
        await callback.answer()

    @router.callback_query(StatsCB.filter(F.action == StatsAction.ME))
    async def cb_profile(callback: CallbackQuery) -> None:
        if callback.message is None:
            await callback.answer(Errors.STALE_BUTTON, show_alert=True)
            return
        async with open_stats() as stats:
            profile = await stats.player_profile(callback.message.chat.id, callback.from_user.id)
        await callback.answer(profile_text(profile), show_alert=True)

    return router
