from dataclasses import dataclass

import pytest
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery, DeleteMessage, EditMessageMedia, SendPhoto
from aiogram.types import BufferedInputFile, Update
from fake_bot import CHAT_ID, HOST_ID, SENT_MESSAGE_ID, FakeSession, callback_update, make_bot
from fake_games import FakeGameStateRepository

from undercover.bot.routers.reveal import (
    RevealAction,
    RevealCB,
    create_reveal_router,
    start_reveal,
)
from undercover.texts import Buttons, Errors, Reveal
from undercover.game.models import GameSessionState, GameStatus, PlayerState
from undercover.media.card_renderer import (
    render_civilian_card,
    render_hidden_card,
    render_spy_card,
)
from undercover.redis.game_state import GameStateRepository

SESSION_ID = "11111111-1111-1111-1111-111111111111"
NAMES = ("Аня", "Борис", "Вера", "Галя")
SPY_INDEX = 1
WORD = "пицца"
HINT = "её режут на куски"
OUTSIDER_ID = HOST_ID + 1


def make_state(**overrides: object) -> GameSessionState:
    defaults: dict[str, object] = {
        "session_id": SESSION_ID,
        "chat_id": CHAT_ID,
        "host_user_id": HOST_ID,
        "status": GameStatus.REVEAL,
        "players": [
            PlayerState(order_index=index, name=name, is_spy=index == SPY_INDEX)
            for index, name in enumerate(NAMES)
        ],
        "word_id": 42,
        "word_text": WORD,
        "hint_by_spy": {SPY_INDEX: HINT},
    }
    return GameSessionState.model_validate(defaults | overrides)


class RecordingStarter:
    def __init__(self) -> None:
        self.states: list[GameSessionState] = []

    async def __call__(
        self, bot: Bot, games: GameStateRepository, state: GameSessionState
    ) -> None:
        self.states.append(state.model_copy(deep=True))


@dataclass(frozen=True, slots=True)
class Screen:
    photo: bytes | str
    caption: str
    button_text: str
    button: RevealCB


def screens(session: FakeSession) -> list[Screen]:
    result: list[Screen] = []
    for request in session.requests:
        if isinstance(request, SendPhoto):
            photo, caption, markup = request.photo, request.caption, request.reply_markup
        elif isinstance(request, EditMessageMedia):
            photo, caption, markup = (
                request.media.media,
                request.media.caption,
                request.reply_markup,
            )
        else:
            continue

        assert markup is not None, "экран партии без кнопки — тупик"
        button = markup.inline_keyboard[0][0]
        assert button.callback_data is not None
        result.append(
            Screen(
                photo=photo.data if isinstance(photo, BufferedInputFile) else photo,
                caption=caption or "",
                button_text=button.text,
                button=RevealCB.unpack(button.callback_data),
            )
        )
    return result


def hidden_screen(order_index: int) -> Screen:
    return Screen(
        photo=render_hidden_card(NAMES[order_index]),
        caption=Reveal.TURN_CAPTION.format(
            position=order_index + 1, total=len(NAMES), name=NAMES[order_index]
        ),
        button_text=Buttons.SHOW_CARD,
        button=RevealCB(
            action=RevealAction.SHOW, session_id=SESSION_ID, order_index=order_index
        ),
    )


def role_screen(order_index: int) -> Screen:
    name = NAMES[order_index]
    is_last = order_index == len(NAMES) - 1
    return Screen(
        photo=render_spy_card(name, HINT)
        if order_index == SPY_INDEX
        else render_civilian_card(name, WORD),
        caption=(
            Reveal.LAST_VIEWED_CAPTION if is_last else Reveal.VIEWED_CAPTION
        ).format(name=name),
        button_text=Buttons.START_DISCUSSION if is_last else Buttons.NEXT_PLAYER,
        button=RevealCB(
            action=RevealAction.NEXT, session_id=SESSION_ID, order_index=order_index
        ),
    )


@dataclass(frozen=True, slots=True)
class Game:
    bot: Bot
    session: FakeSession
    dispatcher: Dispatcher
    games: FakeGameStateRepository
    starter: RecordingStarter

    async def press(self, screen: Screen, *, user_id: int = HOST_ID) -> None:
        await self.tap(screen.button, user_id=user_id)

    async def tap(self, button: RevealCB, *, user_id: int = HOST_ID) -> None:
        update: Update = callback_update(button.pack(), user_id=user_id)
        await self.dispatcher.feed_update(self.bot, update)

    @property
    def alerts(self) -> list[str | None]:
        return [answer.text for answer in self.session.calls(AnswerCallbackQuery)]


def build_game(state: GameSessionState) -> Game:
    session = FakeSession()
    games = FakeGameStateRepository(state)
    starter = RecordingStarter()
    dispatcher = Dispatcher(games=games)
    dispatcher.include_router(create_reveal_router(starter))
    return Game(make_bot(session), session, dispatcher, games, starter)


@pytest.fixture
def game(state: GameSessionState) -> Game:
    return build_game(state)


@pytest.fixture
def state() -> GameSessionState:
    return make_state()


async def test_full_reveal_cycle_of_four_players(game: Game, state: GameSessionState) -> None:
    await start_reveal(game.bot, game.games, state)

    for order_index in range(len(NAMES)):
        assert screens(game.session)[-1] == hidden_screen(order_index)
        assert game.games.stored.reveal_cursor == order_index
        assert not game.games.stored.players[order_index].has_viewed
        assert game.starter.states == [], "обсуждение не начинается посреди раздачи"

        await game.press(hidden_screen(order_index))
        assert screens(game.session)[-1] == role_screen(order_index)
        assert game.games.stored.players[order_index].has_viewed

        await game.press(role_screen(order_index))

    assert [player.has_viewed for player in game.games.stored.players] == [True] * len(NAMES)
    assert screens(game.session) == [
        screen
        for order_index in range(len(NAMES))
        for screen in (hidden_screen(order_index), role_screen(order_index))
    ]
    assert game.alerts == [None] * (2 * len(NAMES)), "ни одно нажатие не отклонено"


async def test_discussion_starts_strictly_after_the_last_player(
    game: Game, state: GameSessionState
) -> None:
    await start_reveal(game.bot, game.games, state)
    for order_index in range(len(NAMES) - 1):
        await game.press(hidden_screen(order_index))
        assert game.starter.states == []
        await game.press(role_screen(order_index))

    await game.press(hidden_screen(len(NAMES) - 1))
    assert game.starter.states == [], "последний игрок ещё смотрит карточку"

    shown = len(screens(game.session))
    await game.press(role_screen(len(NAMES) - 1))

    started = game.starter.states
    assert len(started) == 1
    assert started[0].status is GameStatus.DISCUSSION
    assert started[0].reveal_cursor == len(NAMES), "курсор ушёл за последнего игрока"
    assert game.games.stored.status is GameStatus.DISCUSSION
    assert len(screens(game.session)) == shown, "экран обсуждения рисует уже другая фаза"


async def test_first_card_starts_the_reveal_phase(
    game: Game, state: GameSessionState
) -> None:
    state.status = GameStatus.SETUP
    state.current_message_id = None

    await start_reveal(game.bot, game.games, state)

    stored = game.games.stored
    assert stored.status is GameStatus.REVEAL
    assert stored.reveal_cursor == 0
    assert stored.current_message_id == SENT_MESSAGE_ID
    assert game.session.calls(SendPhoto), "первая карточка отправляется новым сообщением"


async def test_stale_button_does_not_leak_someone_elses_role(
    game: Game, state: GameSessionState
) -> None:
    await start_reveal(game.bot, game.games, state)
    await game.press(hidden_screen(0))
    await game.press(role_screen(0))
    shown = len(screens(game.session))

    await game.press(hidden_screen(0))

    assert game.alerts[-1] == Errors.STALE_TURN
    assert len(screens(game.session)) == shown, "чужая карточка не открылась"
    assert game.games.stored.reveal_cursor == 1


async def test_outsider_cannot_open_the_card(game: Game, state: GameSessionState) -> None:
    await start_reveal(game.bot, game.games, state)

    await game.press(hidden_screen(0), user_id=OUTSIDER_ID)

    assert game.alerts[-1] == Errors.NOT_HOST
    assert screens(game.session) == [hidden_screen(0)]
    assert not game.games.stored.players[0].has_viewed


async def test_outsider_cannot_skip_the_turn(game: Game, state: GameSessionState) -> None:
    await start_reveal(game.bot, game.games, state)
    await game.press(hidden_screen(0))

    await game.press(role_screen(0), user_id=OUTSIDER_ID)

    assert game.alerts[-1] == Errors.NOT_HOST
    assert game.games.stored.reveal_cursor == 0


async def test_card_cannot_be_opened_twice(game: Game, state: GameSessionState) -> None:
    await start_reveal(game.bot, game.games, state)
    await game.press(hidden_screen(0))
    shown = len(screens(game.session))

    await game.press(hidden_screen(0))

    assert game.alerts[-1] == Reveal.ALREADY_VIEWED
    assert len(screens(game.session)) == shown


async def test_turn_cannot_be_skipped_without_looking(
    game: Game, state: GameSessionState
) -> None:
    await start_reveal(game.bot, game.games, state)

    await game.tap(
        RevealCB(action=RevealAction.NEXT, session_id=SESSION_ID, order_index=0)
    )

    assert game.alerts[-1] == Reveal.NOT_VIEWED_YET
    assert game.games.stored.reveal_cursor == 0
    assert screens(game.session) == [hidden_screen(0)]


async def test_unknown_session_is_reported(game: Game) -> None:
    await game.tap(
        RevealCB(action=RevealAction.SHOW, session_id="нет-такой", order_index=0)
    )

    assert game.alerts == [Errors.SESSION_NOT_FOUND]
    assert not screens(game.session)


@pytest.mark.parametrize("status", [GameStatus.SETUP, GameStatus.DISCUSSION])
async def test_buttons_are_dead_outside_the_reveal_phase(status: GameStatus) -> None:
    game = build_game(make_state(status=status, current_message_id=SENT_MESSAGE_ID))

    await game.tap(hidden_screen(0).button)

    assert game.alerts == [Reveal.WRONG_PHASE]
    assert not screens(game.session)


async def test_spy_without_a_hint_does_not_break_the_bot(
    game: Game, state: GameSessionState
) -> None:
    state.hint_by_spy.clear()
    await start_reveal(game.bot, game.games, state)

    await game.press(hidden_screen(SPY_INDEX - 1))
    await game.press(role_screen(SPY_INDEX - 1))
    await game.press(hidden_screen(SPY_INDEX))

    assert game.alerts[-1] == Errors.BROKEN_SESSION
    assert not game.games.stored.players[SPY_INDEX].has_viewed


async def test_cursor_beyond_the_roster_is_reported() -> None:
    game = build_game(make_state(reveal_cursor=len(NAMES)))

    await game.tap(
        RevealCB(action=RevealAction.SHOW, session_id=SESSION_ID, order_index=len(NAMES))
    )

    assert game.alerts == [Errors.BROKEN_SESSION]
    assert not screens(game.session)


async def test_hidden_card_file_id_is_cached_but_the_role_card_is_not(
    game: Game, state: GameSessionState
) -> None:
    await start_reveal(game.bot, game.games, state)
    cached = game.games.stored.players[0].card_file_id
    assert cached == f"photo-{SENT_MESSAGE_ID}"

    await game.press(hidden_screen(0))

    assert game.games.stored.players[0].card_file_id == cached


async def test_cached_hidden_card_is_not_rendered_again(
    game: Game, state: GameSessionState
) -> None:
    state.players[0].card_file_id = "AgACAgIAA"

    await start_reveal(game.bot, game.games, state)

    (screen,) = screens(game.session)
    assert screen.photo == "AgACAgIAA", "готовый file_id уходит вместо новых байтов"


async def test_uneditable_screen_is_redrawn_as_a_new_message(
    game: Game, state: GameSessionState
) -> None:
    await start_reveal(game.bot, game.games, state)
    game.session.failures[EditMessageMedia] = TelegramBadRequest(
        method=DeleteMessage(chat_id=CHAT_ID, message_id=SENT_MESSAGE_ID),
        message="message can't be edited",
    )

    await game.press(hidden_screen(0))

    assert screens(game.session)[-1] == role_screen(0)
    assert game.games.stored.current_message_id == SENT_MESSAGE_ID + 1
    assert game.games.stored.players[0].has_viewed
