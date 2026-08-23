from undercover.redis.dialog_state import DialogStateRepository


class FakeDialogStateRepository(DialogStateRepository):
    def __init__(self, *chat_ids: int) -> None:
        self._chats = set(chat_ids)

    async def count(self, chat_id: int) -> int:
        return int(chat_id in self._chats)

    async def clear(self, chat_id: int) -> None:
        self._chats.discard(chat_id)

    def opened_in(self, chat_id: int) -> None:
        self._chats.add(chat_id)

    @property
    def is_empty(self) -> bool:
        return not self._chats
