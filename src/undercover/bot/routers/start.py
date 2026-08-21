from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram_dialog import DialogManager, StartMode

from undercover.bot.routers.setup_dialog import Setup
from undercover.texts import Start


def create_start_router() -> Router:
    router = Router(name="start")

    @router.message(CommandStart())
    async def cmd_start(message: Message, dialog_manager: DialogManager) -> None:
        await message.answer(Start.GREETING)
        await dialog_manager.start(Setup.ask_players_count, mode=StartMode.RESET_STACK)

    return router
