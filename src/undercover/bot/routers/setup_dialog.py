import logging
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from operator import itemgetter
from typing import Any, Final, Protocol, TypedDict, cast

from aiogram import Bot
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Chat, Message
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.dialog import OnDialogEvent
from aiogram_dialog.widgets.input import ManagedTextInput, TextInput
from aiogram_dialog.widgets.kbd import (
    Button,
    Column,
    ManagedMultiselect,
    Multiselect,
    Row,
    ScrollingGroup,
)
from aiogram_dialog.widgets.kbd.button import OnClick
from aiogram_dialog.widgets.text import Const, Format, Multi

from undercover.bot.routers.reveal import PhaseStarter
from undercover.game.engine import (
    MAX_NAME_LENGTH,
    MAX_PLAYERS,
    MIN_PLAYERS,
    EmptyWordCatalogError,
    GameRulesError,
    WordsSource,
    create_session,
    max_spies_count,
)
from undercover.redis.game_state import GameStateRepository
from undercover.texts import Buttons, empty_catalog_text
from undercover.texts import Setup as SetupTexts
from undercover.utils.secure_random import secure_rng

logger = logging.getLogger(__name__)


class CategoryRecord(Protocol):
    @property
    def id(self) -> int: ...

    @property
    def title(self) -> str: ...


class Catalog(WordsSource, Protocol):
    async def list_playable_categories(self) -> Sequence[CategoryRecord]: ...


CatalogFactory = Callable[[], AbstractAsyncContextManager[Catalog]]
WordsSourceFactory = Callable[[], AbstractAsyncContextManager[WordsSource]]


class CategoryItem(TypedDict):
    id: int
    title: str


class Setup(StatesGroup):
    ask_players_count = State()
    ask_spies_count = State()
    ask_player_names = State()
    ask_categories = State()
    confirm_start = State()


PLAYERS_COUNT: Final = "players_count"
SPIES_COUNT: Final = "spies_count"
NAMES: Final = "names"
CATEGORIES: Final = "categories"
CHOSEN_CATEGORIES: Final = "chosen_categories"
ERROR: Final = "error"

CATEGORY_PICKER: Final = "category_picker"
CATEGORIES_PER_PAGE: Final = 6
MIN_CATEGORIES_TO_CHOOSE: Final = 2


@dataclass(frozen=True, slots=True)
class SetupDraft:
    players_count: int | None
    spies_count: int | None
    names: tuple[str, ...]
    categories: tuple[CategoryItem, ...]
    chosen_ids: frozenset[int]

    @classmethod
    def read(cls, manager: DialogManager) -> "SetupDraft":
        data = manager.dialog_data
        return cls(
            players_count=data.get(PLAYERS_COUNT),
            spies_count=data.get(SPIES_COUNT),
            names=tuple(data.get(NAMES, ())),
            categories=tuple(data.get(CATEGORIES, ())),
            chosen_ids=frozenset(_category_picker(manager).get_checked()),
        )

    @property
    def chosen_categories(self) -> tuple[CategoryItem, ...]:
        return tuple(item for item in self.categories if item["id"] in self.chosen_ids)

    @property
    def category_ids(self) -> list[int]:
        return [item["id"] for item in self.chosen_categories]

    @property
    def offers_a_choice(self) -> bool:
        return len(self.categories) >= MIN_CATEGORIES_TO_CHOOSE


def create_setup_dialog(open_catalog: CatalogFactory, start_reveal: PhaseStarter) -> Dialog:
    return Dialog(
        Window(
            Multi(
                Const(SetupTexts.ASK_PLAYERS_COUNT),
                Format(SetupTexts.ERROR_PREFIX, when=ERROR),
                sep="\n\n",
            ),
            TextInput(
                id="players_count_input",
                type_factory=_parse_players_count,
                on_success=_on_players_count,
                on_error=_on_input_error,
            ),
            state=Setup.ask_players_count,
            parse_mode=None,
        ),
        Window(
            Multi(
                Format(SetupTexts.ASK_SPIES_COUNT),
                Format(SetupTexts.ERROR_PREFIX, when=ERROR),
                sep="\n\n",
            ),
            TextInput(
                id="spies_count_input",
                type_factory=_parse_count,
                on_success=_on_spies_count,
                on_error=_on_input_error,
            ),
            state=Setup.ask_spies_count,
            parse_mode=None,
        ),
        Window(
            Multi(
                Format(SetupTexts.ASK_PLAYER_NAMES),
                Format(SetupTexts.ERROR_PREFIX, when=ERROR),
                sep="\n\n",
            ),
            TextInput(
                id="name_input",
                type_factory=_parse_name,
                on_success=_on_player_name,
                on_error=_on_input_error,
            ),
            Button(
                Const(Buttons.UNDO_NAME),
                id="undo_name",
                on_click=_on_undo_name,
                when="entered",
            ),
            state=Setup.ask_player_names,
            parse_mode=None,
        ),
        Window(
            Format(SetupTexts.ASK_CATEGORIES),
            ScrollingGroup(
                Column(
                    Multiselect(
                        Format(SetupTexts.CATEGORY_CHOSEN),
                        Format(SetupTexts.CATEGORY_FREE),
                        id=CATEGORY_PICKER,
                        item_id_getter=itemgetter("id"),
                        items=CATEGORIES,
                        type_factory=int,
                    ),
                ),
                id="categories_page",
                height=CATEGORIES_PER_PAGE,
                hide_on_single_page=True,
            ),
            Button(Const(Buttons.CATEGORIES_DONE), id="categories_done", on_click=_on_categories),
            state=Setup.ask_categories,
            parse_mode=None,
        ),
        Window(
            Multi(
                Format(SetupTexts.CONFIRM_START),
                Format(SetupTexts.ERROR_PREFIX, when=ERROR),
                sep="\n\n",
            ),
            Row(
                Button(
                    Const(Buttons.PLAY),
                    id="play",
                    on_click=_play(open_catalog, start_reveal),
                ),
                Button(Const(Buttons.RESTART), id="restart", on_click=_on_restart),
            ),
            Button(
                Const(Buttons.CHANGE_CATEGORIES),
                id="change_categories",
                on_click=_on_change_categories,
                when="has_categories",
            ),
            state=Setup.confirm_start,
            parse_mode=None,
        ),
        on_start=_load_categories(open_catalog),
        getter=_draft_getter,
    )


def _load_categories(open_catalog: CatalogFactory) -> OnDialogEvent:
    async def load(_start_data: Any, dialog_manager: DialogManager) -> None:
        async with open_catalog() as catalog:
            categories = await catalog.list_playable_categories()
        dialog_manager.dialog_data[CATEGORIES] = [
            CategoryItem(id=category.id, title=category.title) for category in categories
        ]

    return load


async def _draft_getter(dialog_manager: DialogManager, **_: Any) -> dict[str, Any]:
    draft = SetupDraft.read(dialog_manager)
    return {
        PLAYERS_COUNT: draft.players_count,
        SPIES_COUNT: draft.spies_count,
        "max_spies": max_spies_count(draft.players_count) if draft.players_count else 1,
        "entered": len(draft.names),
        "names_list": _numbered(draft.names),
        CATEGORIES: list(draft.categories),
        CHOSEN_CATEGORIES: _chosen_titles(draft),
        "has_categories": draft.offers_a_choice,
        ERROR: dialog_manager.dialog_data.get(ERROR),
    }


def _parse_count(text: str) -> int:
    try:
        return int(text.strip())
    except ValueError:
        raise ValueError(SetupTexts.NOT_A_NUMBER) from None


def _parse_players_count(text: str) -> int:
    count = _parse_count(text)
    if not MIN_PLAYERS <= count <= MAX_PLAYERS:
        raise ValueError(SetupTexts.BAD_PLAYERS_COUNT)
    return count


def _parse_name(text: str) -> str:
    name = " ".join(text.split())
    if not name:
        raise ValueError(SetupTexts.EMPTY_NAME)
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(SetupTexts.TOO_LONG_NAME)
    return name


async def _on_input_error(
    _message: Message,
    _widget: ManagedTextInput[Any],
    dialog_manager: DialogManager,
    error: ValueError,
) -> None:
    _set_error(dialog_manager, str(error))


async def _on_players_count(
    _message: Message,
    _widget: ManagedTextInput[int],
    dialog_manager: DialogManager,
    count: int,
) -> None:
    dialog_manager.dialog_data.update({PLAYERS_COUNT: count, NAMES: []})
    dialog_manager.dialog_data.pop(SPIES_COUNT, None)
    _clear_error(dialog_manager)
    await dialog_manager.next()


async def _on_spies_count(
    _message: Message,
    _widget: ManagedTextInput[int],
    dialog_manager: DialogManager,
    count: int,
) -> None:
    draft = SetupDraft.read(dialog_manager)
    if draft.players_count is None:
        await _restart(dialog_manager, SetupTexts.BROKEN_DRAFT)
        return

    limit = max_spies_count(draft.players_count)
    if not 1 <= count <= limit:
        _set_error(
            dialog_manager,
            SetupTexts.BAD_SPIES_COUNT.format(players_count=draft.players_count, max_spies=limit),
        )
        return

    dialog_manager.dialog_data[SPIES_COUNT] = count
    _clear_error(dialog_manager)
    await dialog_manager.next()


async def _on_player_name(
    _message: Message,
    _widget: ManagedTextInput[str],
    dialog_manager: DialogManager,
    name: str,
) -> None:
    draft = SetupDraft.read(dialog_manager)
    if draft.players_count is None:
        await _restart(dialog_manager, SetupTexts.BROKEN_DRAFT)
        return
    if any(existing.casefold() == name.casefold() for existing in draft.names):
        _set_error(dialog_manager, SetupTexts.DUPLICATE_NAME.format(name=name))
        return

    names = [*draft.names, name]
    dialog_manager.dialog_data[NAMES] = names
    _clear_error(dialog_manager)
    if len(names) < draft.players_count:
        return
    if draft.offers_a_choice:
        await dialog_manager.next()
    else:
        await dialog_manager.switch_to(Setup.confirm_start)


async def _on_undo_name(
    _callback: CallbackQuery, _button: Button, dialog_manager: DialogManager
) -> None:
    draft = SetupDraft.read(dialog_manager)
    dialog_manager.dialog_data[NAMES] = list(draft.names[:-1])
    _clear_error(dialog_manager)


async def _on_categories(
    _callback: CallbackQuery, _button: Button, dialog_manager: DialogManager
) -> None:
    await dialog_manager.next()


async def _on_change_categories(
    _callback: CallbackQuery, _button: Button, dialog_manager: DialogManager
) -> None:
    _clear_error(dialog_manager)
    await dialog_manager.switch_to(Setup.ask_categories)


async def _on_restart(
    _callback: CallbackQuery, _button: Button, dialog_manager: DialogManager
) -> None:
    await _restart(dialog_manager)


def _play(open_catalog: CatalogFactory, start_reveal: PhaseStarter) -> OnClick:
    async def on_play(
        callback: CallbackQuery, _button: Button, dialog_manager: DialogManager
    ) -> None:
        draft = SetupDraft.read(dialog_manager)
        if (
            draft.players_count is None
            or draft.spies_count is None
            or len(draft.names) != draft.players_count
        ):
            logger.warning("черновик партии неполон: %r", draft)
            await _restart(dialog_manager, SetupTexts.BROKEN_DRAFT)
            return

        games: GameStateRepository = dialog_manager.middleware_data["games"]
        chat: Chat = dialog_manager.middleware_data["event_chat"]
        bot: Bot = dialog_manager.middleware_data["bot"]
        category_ids = draft.category_ids

        try:
            async with open_catalog() as words:
                state = await create_session(
                    chat_id=chat.id,
                    host_user_id=callback.from_user.id,
                    player_names=draft.names,
                    spies_count=draft.spies_count,
                    words=words,
                    rng=secure_rng(),
                    category_ids=category_ids,
                )
        except EmptyWordCatalogError:
            logger.exception("чат %s: партию не собрать, словарь непригоден", chat.id)
            _set_error(dialog_manager, empty_catalog_text(category_ids))
            return
        except GameRulesError:
            logger.exception("чат %s: черновик %r не прошёл правила игры", chat.id, draft)
            await _restart(dialog_manager, SetupTexts.BROKEN_DRAFT)
            return

        logger.info(
            "чат %s: собрана партия %s на %s игроков (%s шпионов), категории: %s",
            chat.id,
            state.session_id,
            len(state.players),
            draft.spies_count,
            category_ids or "все",
        )
        await dialog_manager.done()
        await start_reveal(bot, games, state)

    return on_play


async def _restart(dialog_manager: DialogManager, error: str | None = None) -> None:
    categories = dialog_manager.dialog_data.get(CATEGORIES, [])
    dialog_manager.dialog_data.clear()
    dialog_manager.dialog_data[CATEGORIES] = categories

    await _category_picker(dialog_manager).reset_checked()

    if error is not None:
        _set_error(dialog_manager, error)
    await dialog_manager.switch_to(Setup.ask_players_count)


def _category_picker(manager: DialogManager) -> ManagedMultiselect[int]:
    return cast(ManagedMultiselect[int], manager.find(CATEGORY_PICKER))


def _chosen_titles(draft: SetupDraft) -> str:
    chosen = draft.chosen_categories
    if not chosen:
        return SetupTexts.ALL_CATEGORIES
    return ", ".join(item["title"] for item in chosen)


def _set_error(dialog_manager: DialogManager, error: str) -> None:
    dialog_manager.dialog_data[ERROR] = error


def _clear_error(dialog_manager: DialogManager) -> None:
    dialog_manager.dialog_data.pop(ERROR, None)


def _numbered(names: tuple[str, ...]) -> str:
    if not names:
        return SetupTexts.NO_NAMES_YET
    return "\n".join(f"{position}. {name}" for position, name in enumerate(names, start=1))
