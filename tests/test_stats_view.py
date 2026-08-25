from typing import Final

from undercover.bot.callbacks import StatsAction, StatsCB
from undercover.bot.stats_view import (
    hall_of_fame_keyboard,
    hall_of_fame_text,
    private_text,
    profile_text,
)
from undercover.game.stats import Champion, ChatTotals, HallOfFame, PlayerProfile
from undercover.texts import Buttons, Stats

ALERT_LIMIT: Final = 200
TOTALS: Final = ChatTotals(games=34, civilian_wins=19, spy_wins=12)

FULL: Final = HallOfFame(
    totals=TOTALS,
    spy_of_the_month=Champion(name="Аня", value=5, total=6),
    best_detective=Champion(name="Борис", value=9, total=11),
    first_victim=Champion(name="Вера", value=7),
    longest_streak=Champion(name="Галя", value=4),
)


def test_the_board_names_every_title_it_has() -> None:
    text = hall_of_fame_text(FULL)

    assert "Шпион месяца: Аня — 5 из 6 за шпиона" in text
    assert "Лучший сыщик: Борис — 9 из 11 за мирного" in text
    assert "Первая жертва: Вера — 7 раз" in text
    assert "Серия побед: Галя — 4 подряд" in text


def test_a_title_without_a_holder_takes_no_line() -> None:
    text = hall_of_fame_text(HallOfFame(totals=TOTALS, first_victim=Champion(name="Вера", value=2)))

    assert "Первая жертва: Вера — 2 раза" in text
    assert "Лучший сыщик" not in text


def test_a_chat_with_games_but_no_titles_is_told_to_play_more() -> None:
    assert Stats.NO_TITLES in hall_of_fame_text(HallOfFame(totals=TOTALS))


def test_a_chat_that_never_finished_a_game_says_exactly_that() -> None:
    empty = HallOfFame(totals=ChatTotals(games=0, civilian_wins=0, spy_wins=0))

    assert Stats.NO_GAMES in hall_of_fame_text(empty)


def test_the_board_counts_both_sides() -> None:
    assert "Партий в этом чате: 34 — мирные взяли 19, шпионы 12." in hall_of_fame_text(FULL)


def test_the_board_offers_the_private_card() -> None:
    (row,) = hall_of_fame_keyboard().inline_keyboard
    (item,) = row

    assert item.text == Buttons.MY_STATS
    assert item.callback_data == StatsCB(action=StatsAction.ME).pack()


def test_the_private_screen_explains_where_the_hall_lives() -> None:
    text = private_text(ChatTotals(games=8, civilian_wins=4, spy_wins=3))

    assert "Партий с этого телефона: 8 — мирные взяли 4, шпионы 3." in text
    assert Stats.PRIVATE in text


def test_a_newcomer_is_told_they_have_not_played() -> None:
    assert profile_text(None) == Stats.NO_PROFILE


def test_the_card_splits_the_roles_and_counts_the_streak() -> None:
    text = profile_text(
        PlayerProfile(games=12, wins=7, spy_games=5, spy_wins=4, streak=2, first_outs=3)
    )

    assert text.splitlines() == [
        "Партий: 12 · Побед: 7 (58%)",
        "За шпиона: 4 из 5",
        "За мирного: 3 из 7",
        "Серия побед: 2",
        "Вылетали первым: 3 раза",
    ]


def test_the_card_stays_silent_about_what_never_happened() -> None:
    text = profile_text(
        PlayerProfile(games=3, wins=0, spy_games=0, spy_wins=0, streak=0, first_outs=0)
    )

    assert text.splitlines() == ["Партий: 3 · Побед: 0 (0%)", "За мирного: 0 из 3"]


def test_the_card_fits_into_a_telegram_alert() -> None:
    text = profile_text(
        PlayerProfile(games=999, wins=999, spy_games=333, spy_wins=333, streak=999, first_outs=999)
    )

    assert len(text) <= ALERT_LIMIT
