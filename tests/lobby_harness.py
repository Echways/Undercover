from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import InlineKeyboardMarkup

from fake_bot import HOST_ID, FakeSession, callback_update, message_update
from fake_games import FakeGameStateRepository
from fake_lobbies import FakeLobbyRepository
from fake_words import FakeWords


@dataclass(frozen=True, slots=True)
class Screen:
    text: str
    buttons: tuple[tuple[str, str], ...]

    @property
    def texts(self) -> tuple[str, ...]:
        return tuple(text for text, _ in self.buttons)

    def callback_data(self, button_text: str) -> str:
        found = dict(self.buttons).get(button_text)
        assert found is not None, f"на экране нет кнопки «{button_text}»: {self.texts}"
        return found


@dataclass(frozen=True, slots=True)
class Group:
    dispatcher: Dispatcher
    bot: Bot
    session: FakeSession
    games: FakeGameStateRepository
    lobbies: FakeLobbyRepository
    words: FakeWords

    async def command(self, text: str, *, user_id: int = HOST_ID) -> None:
        await self.dispatcher.feed_update(
            self.bot, message_update(text, user_id=user_id, update_id=self._next_update)
        )

    async def press(self, button_text: str, *, user_id: int = HOST_ID) -> None:
        await self.tap(self.screen.callback_data(button_text), user_id=user_id)

    async def tap(self, data: str, *, user_id: int = HOST_ID) -> None:
        await self.dispatcher.feed_update(
            self.bot, callback_update(data, user_id=user_id, update_id=self._next_update)
        )

    @property
    def screen(self) -> Screen:
        screens = self.screens
        assert screens, "лобби ещё не нарисовано"
        return screens[-1]

    @property
    def screens(self) -> list[Screen]:
        result: list[Screen] = []
        for request in self.session.requests:
            if not isinstance(request, SendMessage | EditMessageText):
                continue
            markup = request.reply_markup
            rows = markup.inline_keyboard if isinstance(markup, InlineKeyboardMarkup) else []
            result.append(
                Screen(
                    text=request.text or "",
                    buttons=tuple(
                        (item.text, item.callback_data)
                        for row in rows
                        for item in row
                        if item.callback_data is not None
                    ),
                )
            )
        return result

    @property
    def alerts(self) -> list[str | None]:
        return [answer.text for answer in self.session.calls(AnswerCallbackQuery)]

    @property
    def redirects(self) -> list[str | None]:
        return [answer.url for answer in self.session.calls(AnswerCallbackQuery)]

    @property
    def _next_update(self) -> int:
        return len(self.session.requests) + 1
