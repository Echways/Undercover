from typing import Final

from fake_words import catalog
from undercover.bot.callbacks import LobbyAction, LobbyCB, StatsAction, StatsCB
from undercover.bot.lobby_view import lobby_keyboard, lobby_text
from undercover.game.engine import MAX_PLAYERS
from undercover.game.models import (
    DEFAULT_TURN_SECONDS,
    LobbyPlayer,
    LobbyState,
    LobbyView,
    Ruleset,
)
from undercover.texts import RULESET_LINES, RULESET_NAMES, Buttons, Lobby

CHAT_ID: Final = -1001234567890
CATALOG: Final = catalog("Еда", "Города")


def lobby(players: int = 0, **overrides: object) -> LobbyState:
    defaults: dict[str, object] = {
        "chat_id": CHAT_ID,
        "host_user_id": 777,
        "players": [LobbyPlayer(user_id=index, name=f"Игрок-{index}") for index in range(players)],
    }
    return LobbyState.model_validate(defaults | overrides)


def texts_of(lobby_state: LobbyState) -> list[str]:
    return [
        item.text for row in lobby_keyboard(lobby_state, CATALOG).inline_keyboard for item in row
    ]


def test_an_empty_lobby_says_so_instead_of_showing_an_empty_list() -> None:
    assert Lobby.EMPTY_ROSTER in lobby_text(lobby(), CATALOG)


def test_the_roster_is_numbered_from_one_and_shows_the_ceiling() -> None:
    text = lobby_text(lobby(2), CATALOG)

    assert "1. Игрок-0" in text
    assert "2. Игрок-1" in text
    assert str(MAX_PLAYERS) in text


def test_the_summary_says_whole_dictionary_when_nothing_is_chosen() -> None:
    assert "весь словарь" in lobby_text(lobby(3), CATALOG)


def test_the_summary_lists_the_chosen_categories_by_title() -> None:
    text = lobby_text(lobby(3, settings={"category_ids": [1]}), CATALOG)

    assert "Еда" in text
    assert "Города" not in text


def test_the_roster_keyboard_carries_join_leave_settings_hall_and_start() -> None:
    assert texts_of(lobby(2)) == [
        Buttons.JOIN_LOBBY,
        Buttons.LEAVE_LOBBY,
        Buttons.SPIES_COUNT.format(count=1),
        Buttons.TURN_LIMIT.format(seconds=DEFAULT_TURN_SECONDS),
        Buttons.RULESET.format(name=RULESET_NAMES[Ruleset.CLASSIC]),
        Buttons.CHANGE_CATEGORIES,
        Buttons.RULES,
        Buttons.HALL_OF_FAME,
        Buttons.PLAY,
    ]


def test_the_roster_offers_the_hall_of_fame() -> None:
    assert Buttons.HALL_OF_FAME in texts_of(lobby(3))


def test_the_hall_of_fame_button_carries_the_stats_callback() -> None:
    rows = lobby_keyboard(lobby(3), CATALOG).inline_keyboard
    item = next(button for row in rows for button in row if button.text == Buttons.HALL_OF_FAME)

    assert item.callback_data == StatsCB(action=StatsAction.BOARD).pack()


def test_the_reading_buttons_do_not_crowd_the_start_button() -> None:
    rows = lobby_keyboard(lobby(3), CATALOG).inline_keyboard
    last_two = [[item.text for item in row] for row in rows[-2:]]

    assert last_two == [[Buttons.RULES, Buttons.HALL_OF_FAME], [Buttons.PLAY]]


def test_the_roster_tells_newcomers_what_the_game_is_about() -> None:
    assert Lobby.SYNOPSIS in lobby_text(lobby(), CATALOG)


def test_the_summary_names_the_ruleset_and_what_it_costs() -> None:
    classic = lobby_text(lobby(3), CATALOG)
    sudden_death = lobby_text(lobby(3, settings={"ruleset": Ruleset.SUDDEN_DEATH}), CATALOG)

    assert RULESET_LINES[Ruleset.CLASSIC] in classic
    assert RULESET_LINES[Ruleset.SUDDEN_DEATH] in sudden_death


def test_the_ruleset_button_shows_the_mode_the_table_plays() -> None:
    sudden_death = Buttons.RULESET.format(name=RULESET_NAMES[Ruleset.SUDDEN_DEATH])

    assert sudden_death in texts_of(lobby(3, settings={"ruleset": Ruleset.SUDDEN_DEATH}))
    assert sudden_death not in texts_of(lobby(3))


def test_the_category_view_hides_the_rules_and_the_ruleset() -> None:
    state = lobby(2, view=LobbyView.CATEGORIES)

    assert Buttons.RULES not in texts_of(state)


def test_a_one_category_dictionary_offers_no_choice() -> None:
    single = [
        item.text
        for row in lobby_keyboard(lobby(2), catalog("Еда")).inline_keyboard
        for item in row
    ]

    assert Buttons.CHANGE_CATEGORIES not in single
    assert Buttons.JOIN_LOBBY in single


def test_the_category_view_marks_the_chosen_ones_and_offers_done() -> None:
    state = lobby(2, view=LobbyView.CATEGORIES, settings={"category_ids": [1]})

    assert Lobby.PICK_CATEGORIES in lobby_text(state, CATALOG)
    assert texts_of(state) == [
        Lobby.CATEGORY_CHOSEN.format(title="Еда"),
        Lobby.CATEGORY_FREE.format(title="Города"),
        Buttons.CATEGORIES_DONE,
    ]


def test_callback_data_fits_the_telegram_limit() -> None:
    packed = LobbyCB(action=LobbyAction.CATEGORY, value=999999).pack()

    assert len(packed.encode()) <= 64


def test_the_turn_button_shows_the_current_length() -> None:
    assert Buttons.TURN_LIMIT.format(seconds=DEFAULT_TURN_SECONDS) in texts_of(lobby(2))


def test_the_turn_button_says_plainly_when_the_timer_is_off() -> None:
    assert Buttons.TURN_OFF in texts_of(lobby(2, settings={"turn_seconds": 0}))
