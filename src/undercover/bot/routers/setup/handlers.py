from collections.abc import Sequence
from typing import Any

from aiogram.types import CallbackQuery, Message
from aiogram_dialog import DialogManager
from aiogram_dialog.dialog import OnDialogEvent
from aiogram_dialog.widgets.input import ManagedTextInput
from aiogram_dialog.widgets.kbd import Button

from undercover.bot.routers.setup.draft import (
    CATEGORIES,
    CHOSEN_CATEGORIES,
    ERROR,
    NAMES,
    PLAYERS_COUNT,
    CategoryItem,
    SetupDraft,
    clear_error,
    numbered,
    restart,
    set_error,
)
from undercover.bot.routers.setup.states import Setup
from undercover.game.catalog import CachedCatalog
from undercover.game.engine import secure_rng
from undercover.game.nicknames import pick_nicknames
from undercover.game.settings import (
    clamp_spies,
    cycle_spies,
    cycle_turn_seconds,
    toggle_ruleset,
)
from undercover.texts import Setup as SetupTexts
from undercover.texts import chosen_categories_text, ruleset_label, spies_label, turn_label


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
        "spies_label": spies_label(draft.settings.spies_count),
        "turn_label": turn_label(draft.settings.turn_seconds),
        "ruleset_label": ruleset_label(draft.settings.ruleset),
        "spies_count": draft.settings.spies_count,
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
    draft = SetupDraft.read(dialog_manager)
    clamp_spies(draft.settings, count)
    draft.save(dialog_manager)
    clear_error(dialog_manager)
    await dialog_manager.next()


async def on_spies(
    _callback: CallbackQuery, _button: Button, dialog_manager: DialogManager
) -> None:
    draft = SetupDraft.read(dialog_manager)
    cycle_spies(draft.settings, draft.players_count or 0)
    draft.save(dialog_manager)


async def on_turn_seconds(
    _callback: CallbackQuery, _button: Button, dialog_manager: DialogManager
) -> None:
    draft = SetupDraft.read(dialog_manager)
    cycle_turn_seconds(draft.settings)
    draft.save(dialog_manager)


async def on_ruleset(
    _callback: CallbackQuery, _button: Button, dialog_manager: DialogManager
) -> None:
    draft = SetupDraft.read(dialog_manager)
    toggle_ruleset(draft.settings)
    draft.save(dialog_manager)


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
