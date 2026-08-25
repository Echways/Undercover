from operator import itemgetter

from aiogram_dialog import Dialog, Window
from aiogram_dialog.widgets.input import TextInput
from aiogram_dialog.widgets.kbd import Button, Column, Multiselect, Row, ScrollingGroup
from aiogram_dialog.widgets.text import Const, Format, Multi

from undercover.bot.routers.reveal import PhaseStarter
from undercover.bot.routers.setup_draft import (
    CATEGORIES,
    CATEGORIES_PER_PAGE,
    CATEGORY_PICKER,
    ERROR,
    Setup,
)
from undercover.bot.routers.setup_handlers import (
    draft_getter,
    load_categories,
    on_autofill_names,
    on_categories,
    on_change_categories,
    on_input_error,
    on_player_name,
    on_players_count,
    on_restart,
    on_spies_count,
    on_undo_name,
    parse_count,
    parse_name,
    parse_players_count,
    play,
)
from undercover.game.catalog import CachedCatalog
from undercover.texts import Buttons
from undercover.texts import Setup as SetupTexts


def create_setup_dialog(catalog: CachedCatalog, start_reveal: PhaseStarter) -> Dialog:
    return Dialog(
        Window(
            Multi(
                Const(SetupTexts.ASK_PLAYERS_COUNT),
                Format(SetupTexts.ERROR_PREFIX, when=ERROR),
                sep="\n\n",
            ),
            TextInput(
                id="players_count_input",
                type_factory=parse_players_count,
                on_success=on_players_count,
                on_error=on_input_error,
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
                type_factory=parse_count,
                on_success=on_spies_count,
                on_error=on_input_error,
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
                type_factory=parse_name,
                on_success=on_player_name,
                on_error=on_input_error,
            ),
            Row(
                Button(
                    Const(Buttons.AUTOFILL_NAMES),
                    id="autofill_names",
                    on_click=on_autofill_names,
                ),
                Button(
                    Const(Buttons.UNDO_NAME),
                    id="undo_name",
                    on_click=on_undo_name,
                    when="entered",
                ),
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
            Button(Const(Buttons.CATEGORIES_DONE), id="categories_done", on_click=on_categories),
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
                    on_click=play(catalog, start_reveal),
                ),
                Button(Const(Buttons.RESTART), id="restart", on_click=on_restart),
            ),
            Button(
                Const(Buttons.CHANGE_CATEGORIES),
                id="change_categories",
                on_click=on_change_categories,
                when="has_categories",
            ),
            state=Setup.confirm_start,
            parse_mode=None,
        ),
        on_start=load_categories(catalog),
        getter=draft_getter,
    )
