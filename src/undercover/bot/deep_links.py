import re
from typing import Final

from aiogram import Bot
from aiogram.utils.deep_linking import create_start_link

JOIN_PAYLOAD_PREFIX: Final = "join_"

RULES_PAYLOAD: Final = "rules"

JOIN_PAYLOAD: Final = re.compile(rf"^{JOIN_PAYLOAD_PREFIX}(-?\d+)$")


async def join_link(bot: Bot, chat_id: int) -> str:
    return await create_start_link(bot, f"{JOIN_PAYLOAD_PREFIX}{chat_id}", encode=False)


async def rules_link(bot: Bot) -> str:
    return await create_start_link(bot, RULES_PAYLOAD, encode=False)
