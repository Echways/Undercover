from undercover.game.stats import Champion, ChatTotals, HallOfFame, PlayerProfile


def profile(**overrides: int) -> PlayerProfile:
    defaults = {"games": 10, "wins": 6, "spy_games": 4, "spy_wins": 3, "streak": 2, "first_outs": 1}
    return PlayerProfile(**(defaults | overrides))


def test_the_civilian_side_is_what_is_left_of_the_games() -> None:
    assert (profile().civilian_games, profile().civilian_wins) == (6, 3)


def test_the_win_rate_is_a_whole_percent() -> None:
    assert profile(games=3, wins=1).win_rate == 33


def test_a_hall_without_a_single_title_says_so() -> None:
    empty = HallOfFame(totals=ChatTotals(games=4, civilian_wins=3, spy_wins=1))

    assert not empty.has_titles


def test_one_title_is_enough_to_open_the_hall() -> None:
    hall = HallOfFame(
        totals=ChatTotals(games=4, civilian_wins=3, spy_wins=1),
        first_victim=Champion(name="Вера", value=3),
    )

    assert hall.has_titles
