import pytest
from aiogram.enums import ChatType
from aiogram.types import Message

from fake_bot import message_update
from undercover.bot.filters import IN_GROUP


def message_in(chat_type: ChatType) -> Message:
    message = message_update("/undercover", chat_type=chat_type).message
    assert message is not None
    return message


@pytest.mark.parametrize("chat_type", [ChatType.GROUP, ChatType.SUPERGROUP])
def test_a_group_chat_passes_the_filter(chat_type: ChatType) -> None:
    assert IN_GROUP.resolve(message_in(chat_type))


@pytest.mark.parametrize("chat_type", [ChatType.PRIVATE, ChatType.CHANNEL])
def test_everything_else_is_turned_away(chat_type: ChatType) -> None:
    assert not IN_GROUP.resolve(message_in(chat_type))
