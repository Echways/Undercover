import logging
from collections.abc import Sequence
from typing import Any

from aiogram import Bot
from aiogram.types import CallbackQuery, Chat, Message
from aiogram_dialog import DialogManager
from aiogram_dialog.dialog import OnDialogEvent
from aiogram_dialog.widgets.input import ManagedTextInput
from aiogram_dialog.widgets.kbd import Button
from aiogram_dialog.widgets.kbd.button import OnClick

from undercover.bot.routers.reveal import PhaseStarter
from undercover.bot.routers.setup_draft import (
    CATEGORIES,
    CHOSEN_CATEGORIES,
    ERROR,
    NAMES,
    PLAYERS_COUNT,
    SPIES_COUNT,
    CategoryItem,
    Setup,
    SetupDraft,
    clear_error,
    numbered,
    restart,
    set_error,
)
from undercover.game.catalog import CachedCatalog
from undercover.game.engine import (
    MAX_NAME_LENGTH,
    MAX_PLAYERS,
    MIN_PLAYERS,
    EmptyWordCatalogError,
    GameRulesError,
    create_session,
    max_spies_count,
    secure_rng,
)
from undercover.game.nicknames import pick_nicknames
from undercover.redis.game_state import GameStateRepository
from undercover.texts import Setup as SetupTexts
from undercover.texts import chosen_categories_text, empty_catalog_text

logger = logging.getLogger(__name__)


def parse_count(text: str) -> int:
    try:
        return int(text.strip())
    except ValueError:
        raise ValueError(SetupTexts.NOT_A_NUMBER) from None


def parse_players_count(text: str) -> int:
    count = parse_count(text)
    if not MIN_PLAYERS <= count <= MAX_PLAYERS:
        raise ValueError(SetupTexts.BAD_PLAYERS_COUNT)
    return count


def parse_name(text: str) -> str:
    name = " ".join(text.split())
    if not name:
        raise ValueError(SetupTexts.EMPTY_NAME)
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(SetupTexts.TOO_LONG_NAME)
    return name


def load_categories(catalog: CachedCatalog) -> OnDialogEvent:
    async def load(_start_data: Any, dialog_manager: DialogManager) -> None:
        dialog_manager.dialog_data[CATEGORIES] = [
            CategoryItem(id=category.id, title=category.title)
            for category in await catalog.categories()
        ]

    return load


async def draft_getter(dialog_manager: DialogManager, **_: Any) -> dict[str, Any]:
    draft = SetupDraft.read(dialog_manager)
    return {
        PLAYERS_COUNT: draft.players_count,
        SPIES_COUNT: draft.spies_count,
        "max_spies": max_spies_count(draft.players_count) if draft.players_count else 1,
        "entered": len(draft.names),
        "names_list": numbered(draft.names),
        CATEGORIES: list(draft.categories),
        CHOSEN_CATEGORIES: chosen_categories_text(
            item["title"] for item in draft.chosen_categories
        ),
        "has_categories": draft.offers_a_choice,
        ERROR: dialog_manager.dialog_data.get(ERROR),
    }


async def on_input_error(
    _message: Message,
    _widget: ManagedTextInput[Any],
    dialog_manager: DialogManager,
    error: ValueError,
) -> None:
    set_error(dialog_manager, str(error))


async def on_players_count(
    _message: Message,
    _widget: ManagedTextInput[int],
    dialog_manager: DialogManager,
    count: int,
) -> None:
    dialog_manager.dialog_data.update({PLAYERS_COUNT: count, NAMES: []})
    dialog_manager.dialog_data.pop(SPIES_COUNT, None)
    clear_error(dialog_manager)
    await dialog_manager.next()


async def on_spies_count(
    _message: Message,
    _widget: ManagedTextInput[int],
    dialog_manager: DialogManager,
    count: int,
) -> None:
    draft = SetupDraft.read(dialog_manager)
    if draft.players_count is None:
        await restart(dialog_manager, SetupTexts.BROKEN_DRAFT)
        return

    limit = max_spies_count(draft.players_count)
    if not 1 <= count <= limit:
        set_error(
            dialog_manager,
            SetupTexts.BAD_SPIES_COUNT.format(players_count=draft.players_count, max_spies=limit),
        )
        return

    dialog_manager.dialog_data[SPIES_COUNT] = count
    clear_error(dialog_manager)
    await dialog_manager.next()


async def on_player_name(
    _message: Message,
    _widget: ManagedTextInput[str],
    dialog_manager: DialogManager,
    name: str,
) -> None:
    draft = SetupDraft.read(dialog_manager)
    if draft.players_count is None:
        await restart(dialog_manager, SetupTexts.BROKEN_DRAFT)
        return
    if any(existing.casefold() == name.casefold() for existing in draft.names):
        set_error(dialog_manager, SetupTexts.DUPLICATE_NAME.format(name=name))
        return

    await _seat_players(dialog_manager, draft, (name,))


async def on_autofill_names(
    _callback: CallbackQuery, _button: Button, dialog_manager: DialogManager
) -> None:
    draft = SetupDraft.read(dialog_manager)
    if draft.players_count is None:
        await restart(dialog_manager, SetupTexts.BROKEN_DRAFT)
        return

    nicknames = pick_nicknames(draft.free_slots, draft.names, secure_rng())
    await _seat_players(dialog_manager, draft, nicknames)


async def on_undo_name(
    _callback: CallbackQuery, _button: Button, dialog_manager: DialogManager
) -> None:
    draft = SetupDraft.read(dialog_manager)
    dialog_manager.dialog_data[NAMES] = list(draft.names[:-1])
    clear_error(dialog_manager)


async def on_categories(
    _callback: CallbackQuery, _button: Button, dialog_manager: DialogManager
) -> None:
    await dialog_manager.next()


async def on_change_categories(
    _callback: CallbackQuery, _button: Button, dialog_manager: DialogManager
) -> None:
    clear_error(dialog_manager)
    await dialog_manager.switch_to(Setup.ask_categories)


async def on_restart(
    _callback: CallbackQuery, _button: Button, dialog_manager: DialogManager
) -> None:
    await restart(dialog_manager)


def play(catalog: CachedCatalog, start_reveal: PhaseStarter) -> OnClick:
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
            await restart(dialog_manager, SetupTexts.BROKEN_DRAFT)
            return

        games: GameStateRepository = dialog_manager.middleware_data["games"]
        chat: Chat = dialog_manager.middleware_data["event_chat"]
        bot: Bot = dialog_manager.middleware_data["bot"]
        category_ids = draft.category_ids

        try:
            async with catalog.open() as words:
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
            set_error(dialog_manager, empty_catalog_text(category_ids))
            return
        except GameRulesError:
            logger.exception("чат %s: черновик %r не прошёл правила игры", chat.id, draft)
            await restart(dialog_manager, SetupTexts.BROKEN_DRAFT)
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


async def _seat_players(
    dialog_manager: DialogManager, draft: SetupDraft, arriving: Sequence[str]
) -> None:
    dialog_manager.dialog_data[NAMES] = [*draft.names, *arriving]
    clear_error(dialog_manager)
    if len(arriving) < draft.free_slots:
        return
    if draft.offers_a_choice:
        await dialog_manager.next()
    else:
        await dialog_manager.switch_to(Setup.confirm_start)
