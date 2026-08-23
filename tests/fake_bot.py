from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from itertools import count
from typing import Any, Final

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import (
    AnswerCallbackQuery,
    DeleteMessage,
    EditMessageCaption,
    EditMessageMedia,
    EditMessageText,
    GetChatMember,
    GetMe,
    SendMessage,
    SendPhoto,
    SetMyCommands,
    TelegramMethod,
)
from aiogram.types import (
    CallbackQuery,
    Chat,
    ChatMemberAdministrator,
    ChatMemberMember,
    Message,
    PhotoSize,
    Update,
    User,
)

TOKEN: Final = "424242:AA-fake-bot-token"

CHAT_ID: Final = -1001234567890
HOST_ID: Final = 777
FIRST_MESSAGE_ID: Final = 1000

SENT_MESSAGE_ID: Final = 2000


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod[Any]] = []
        self.failures: dict[type[TelegramMethod[Any]], Exception] = {}
        self.results: dict[type[TelegramMethod[Any]], list[Any]] = {}
        self._message_ids = count(SENT_MESSAGE_ID)

    async def make_request(
        self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None
    ) -> Any:
        self.requests.append(method)

        failure = self.failures.pop(type(method), None)
        if failure is not None:
            raise failure

        queued = self.results.get(type(method))
        if queued:
            return queued.pop(0)
        return self._default_result(method)

    async def close(self) -> None:
        return None

    def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes]:
        raise NotImplementedError("тесты не качают файлы")

    def calls(self, method: type[TelegramMethod[Any]]) -> list[Any]:
        return [request for request in self.requests if isinstance(request, method)]

    def _default_result(self, method: TelegramMethod[Any]) -> Any:
        if isinstance(method, SendPhoto):
            return photo_message(next(self._message_ids))
        if isinstance(method, EditMessageMedia):
            assert method.message_id is not None
            return photo_message(method.message_id)
        if isinstance(method, EditMessageCaption):
            assert method.message_id is not None
            return photo_message(method.message_id)
        if isinstance(method, EditMessageText):
            assert method.message_id is not None
            return text_message(method.message_id, method.text or "")
        if isinstance(method, GetChatMember):
            return chat_member(method.user_id)
        if isinstance(method, GetMe):
            return User(id=1, is_bot=True, first_name="Undercover", username="undercover_bot")
        if isinstance(method, SendMessage):
            return text_message(next(self._message_ids), method.text)
        if isinstance(method, (DeleteMessage, AnswerCallbackQuery, SetMyCommands)):
            return True
        raise AssertionError(f"тест не ждал вызова {type(method).__name__}")


def chat_member(user_id: int) -> ChatMemberMember:
    return ChatMemberMember(user=User(id=user_id, is_bot=False, first_name="Игрок"))


def chat_admin(user_id: int) -> ChatMemberAdministrator:
    return ChatMemberAdministrator(
        user=User(id=user_id, is_bot=False, first_name="Админ"),
        can_be_edited=False,
        is_anonymous=False,
        can_manage_chat=True,
        can_delete_messages=True,
        can_manage_video_chats=True,
        can_restrict_members=True,
        can_promote_members=False,
        can_change_info=True,
        can_invite_users=True,
        can_post_stories=False,
        can_edit_stories=False,
        can_delete_stories=False,
    )


def photo_message(message_id: int, chat_id: int = CHAT_ID) -> Message:
    return Message(
        message_id=message_id,
        date=datetime.now(UTC),
        chat=Chat(id=chat_id, type="group"),
        photo=[
            PhotoSize(
                file_id=f"photo-{message_id}",
                file_unique_id=f"unique-{message_id}",
                width=1080,
                height=1350,
            )
        ],
    )


def text_message(message_id: int, text: str, chat_id: int = CHAT_ID) -> Message:
    return Message(
        message_id=message_id,
        date=datetime.now(UTC),
        chat=Chat(id=chat_id, type="group"),
        text=text,
    )


def make_bot(session: FakeSession) -> Bot:
    return Bot(token=TOKEN, session=session)


def callback_update(
    data: str,
    *,
    user_id: int = HOST_ID,
    message_id: int = FIRST_MESSAGE_ID,
    chat_id: int = CHAT_ID,
    update_id: int = 1,
) -> Update:
    return Update(
        update_id=update_id,
        callback_query=CallbackQuery(
            id=f"cb-{update_id}",
            from_user=User(id=user_id, is_bot=False, first_name="Ведущий"),
            chat_instance=f"chat-instance-{chat_id}",
            data=data,
            message=photo_message(message_id, chat_id),
        ),
    )


def message_update(
    text: str,
    *,
    user_id: int = HOST_ID,
    chat_id: int = CHAT_ID,
    chat_type: str = "group",
    update_id: int = 1,
) -> Update:
    return Update(
        update_id=update_id,
        message=Message(
            message_id=update_id,
            date=datetime.now(UTC),
            chat=Chat(id=chat_id, type=chat_type),
            from_user=User(id=user_id, is_bot=False, first_name="Ведущий"),
            text=text,
        ),
    )
