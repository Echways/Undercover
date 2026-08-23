from typing import Final

from aiogram import F
from aiogram.enums import ChatType

IN_GROUP: Final = F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP})
