from dataclasses import dataclass
from typing import Final, TypedDict, cast

from aiogram_dialog import DialogManager
from aiogram_dialog.widgets.kbd import ManagedMultiselect

from undercover.bot.routers.setup.states import Setup
from undercover.game.engine import offers_a_choice
from undercover.game.settings import GameSettings
from undercover.texts import Setup as SetupTexts


class CategoryItem(TypedDict):
    id: int
    title: str


PLAYERS_COUNT: Final = "players_count"
SETTINGS: Final = "settings"
NAMES: Final = "names"
CATEGORIES: Final = "categories"
CHOSEN_CATEGORIES: Final = "chosen_categories"
ERROR: Final = "error"

CATEGORY_PICKER: Final = "category_picker"
CATEGORIES_PER_PAGE: Final = 6


@dataclass(frozen=True, slots=True)
class SetupDraft:
    players_count: int | None
    settings: GameSettings
    names: tuple[str, ...]
    categories: tuple[CategoryItem, ...]
    chosen_ids: frozenset[int]

    @classmethod
    def read(cls, manager: DialogManager) -> "SetupDraft":
        data = manager.dialog_data
        return cls(
            players_count=data.get(PLAYERS_COUNT),
            settings=GameSettings.model_validate(data.get(SETTINGS, {})),
            names=tuple(data.get(NAMES, ())),
            categories=tuple(data.get(CATEGORIES, ())),
            chosen_ids=frozenset(category_picker(manager).get_checked()),
        )

    def save(self, manager: DialogManager) -> None:
        manager.dialog_data[SETTINGS] = self.settings.model_dump(mode="json")

    @property
    def chosen_categories(self) -> tuple[CategoryItem, ...]:
        return tuple(item for item in self.categories if item["id"] in self.chosen_ids)

    @property
    def category_ids(self) -> list[int]:
        return [item["id"] for item in self.chosen_categories]

    @property
    def free_slots(self) -> int:
        if self.players_count is None:
            return 0
        return self.players_count - len(self.names)

    @property
    def offers_a_choice(self) -> bool:
        return offers_a_choice(self.categories)


def category_picker(manager: DialogManager) -> ManagedMultiselect[int]:
    return cast(ManagedMultiselect[int], manager.find(CATEGORY_PICKER))


def set_error(dialog_manager: DialogManager, error: str) -> None:
    dialog_manager.dialog_data[ERROR] = error


def clear_error(dialog_manager: DialogManager) -> None:
    dialog_manager.dialog_data.pop(ERROR, None)


async def restart(dialog_manager: DialogManager, error: str | None = None) -> None:
    categories = dialog_manager.dialog_data.get(CATEGORIES, [])
    dialog_manager.dialog_data.clear()
    dialog_manager.dialog_data[CATEGORIES] = categories

    await category_picker(dialog_manager).reset_checked()

    if error is not None:
        set_error(dialog_manager, error)
    await dialog_manager.switch_to(Setup.ask_players_count)


def numbered(names: tuple[str, ...]) -> str:
    if not names:
        return SetupTexts.NO_NAMES_YET
    return "\n".join(f"{position}. {name}" for position, name in enumerate(names, start=1))
