from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from undercover.db.models import Category, GamePlayerResult, GameSessionLog, SpyHint, Word
from undercover.db.repositories.stats import StatsRepository
from undercover.game.models import Winner
from undercover.game.stats import Champion, StatsSource

pytestmark = pytest.mark.integration

CHAT_ID = -100777
HOST_ID = 777
NOW = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class Seat:
    user_id: int
    name: str
    is_spy: bool = False
    out_order: int | None = None


@pytest.fixture
async def word(db_session: AsyncSession) -> Word:
    item = Word(text="пицца", hints=[SpyHint(hint_text="её режут на куски")])
    db_session.add(Category(slug="food-stats", title="Еда", words=[item]))
    await db_session.flush()
    return item


async def play(
    session: AsyncSession,
    word: Word,
    *seats: Seat,
    winner: Winner | None = Winner.CIVILIANS,
    ago: timedelta = timedelta(),
) -> None:
    at = NOW - ago
    session.add(
        GameSessionLog(
            chat_id=CHAT_ID,
            host_user_id=HOST_ID,
            players_count=len(seats),
            spies_count=sum(seat.is_spy for seat in seats),
            word_id=word.id,
            winner=winner,
            started_at=at - timedelta(minutes=10),
            finished_at=at,
            players=_rows(seats, winner, at),
        )
    )
    await session.flush()


def _rows(seats: tuple[Seat, ...], winner: Winner | None, at: datetime) -> list[GamePlayerResult]:
    if winner is None:
        return []
    return [
        GamePlayerResult(
            chat_id=CHAT_ID,
            user_id=seat.user_id,
            name=seat.name,
            is_spy=seat.is_spy,
            is_winner=(winner is Winner.SPIES) == seat.is_spy,
            out_order=seat.out_order,
            finished_at=at,
        )
        for seat in seats
    ]


async def test_an_empty_chat_has_played_nothing(db_session: AsyncSession) -> None:
    totals = await StatsRepository(db_session).chat_totals(CHAT_ID)

    assert totals.games == 0


async def test_the_totals_count_every_finished_game_and_both_sides(
    db_session: AsyncSession, word: Word
) -> None:
    await play(db_session, word, Seat(1, "Аня", is_spy=True), Seat(2, "Борис"))
    await play(db_session, word, Seat(1, "Аня"), Seat(2, "Борис", is_spy=True), winner=Winner.SPIES)
    await play(db_session, word, Seat(1, "Аня"), Seat(2, "Борис"), winner=None)

    totals = await StatsRepository(db_session).chat_totals(CHAT_ID)

    assert (totals.games, totals.civilian_wins, totals.spy_wins) == (3, 1, 1)


async def test_a_stranger_to_the_chat_has_no_profile(db_session: AsyncSession, word: Word) -> None:
    await play(db_session, word, Seat(1, "Аня"), Seat(2, "Борис"))

    assert await StatsRepository(db_session).player_profile(CHAT_ID, 999) is None


async def test_a_profile_keeps_the_two_roles_apart(db_session: AsyncSession, word: Word) -> None:
    await play(db_session, word, Seat(1, "Аня", is_spy=True), Seat(2, "Борис"), winner=Winner.SPIES)
    await play(db_session, word, Seat(1, "Аня"), Seat(2, "Борис", is_spy=True))
    await play(db_session, word, Seat(1, "Аня"), Seat(2, "Борис", is_spy=True), winner=Winner.SPIES)

    profile = await StatsRepository(db_session).player_profile(CHAT_ID, 1)

    assert profile is not None
    assert (profile.games, profile.wins) == (3, 2)
    assert (profile.spy_games, profile.spy_wins) == (1, 1)
    assert (profile.civilian_games, profile.civilian_wins) == (2, 1)


async def test_a_profile_counts_how_often_the_player_fell_first(
    db_session: AsyncSession, word: Word
) -> None:
    await play(db_session, word, Seat(1, "Аня", out_order=1), Seat(2, "Борис"))
    await play(db_session, word, Seat(1, "Аня", out_order=2), Seat(2, "Борис"))

    profile = await StatsRepository(db_session).player_profile(CHAT_ID, 1)

    assert profile is not None
    assert profile.first_outs == 1


async def test_a_personal_streak_stops_at_the_last_defeat(
    db_session: AsyncSession, word: Word
) -> None:
    await play(db_session, word, Seat(1, "Аня"), Seat(2, "Борис"), ago=timedelta(days=3))
    await play(
        db_session,
        word,
        Seat(1, "Аня"),
        Seat(2, "Борис"),
        winner=Winner.SPIES,
        ago=timedelta(days=2),
    )
    await play(db_session, word, Seat(1, "Аня"), Seat(2, "Борис"), ago=timedelta(days=1))

    profile = await StatsRepository(db_session).player_profile(CHAT_ID, 1)

    assert profile is not None
    assert profile.streak == 1


async def test_a_player_who_never_lost_is_on_a_streak_of_every_game(
    db_session: AsyncSession, word: Word
) -> None:
    await play(db_session, word, Seat(1, "Аня"), Seat(2, "Борис"), ago=timedelta(days=2))
    await play(db_session, word, Seat(1, "Аня"), Seat(2, "Борис"), ago=timedelta(days=1))

    profile = await StatsRepository(db_session).player_profile(CHAT_ID, 1)

    assert profile is not None
    assert profile.streak == 2


async def spy_games(
    session: AsyncSession,
    word: Word,
    *,
    wins: int,
    losses: int,
    ago: timedelta = timedelta(),
) -> None:
    for index in range(wins + losses):
        await play(
            session,
            word,
            Seat(1, "Аня", is_spy=True),
            Seat(2, "Борис"),
            Seat(3, "Вера"),
            winner=Winner.SPIES if index < wins else Winner.CIVILIANS,
            ago=ago,
        )


async def test_a_title_is_not_given_for_two_games(db_session: AsyncSession, word: Word) -> None:
    await spy_games(db_session, word, wins=2, losses=0)

    hall = await StatsRepository(db_session).hall_of_fame(CHAT_ID, NOW)

    assert hall.spy_of_the_month is None


async def test_three_games_in_the_role_open_the_title(db_session: AsyncSession, word: Word) -> None:
    await spy_games(db_session, word, wins=2, losses=1)

    hall = await StatsRepository(db_session).hall_of_fame(CHAT_ID, NOW)

    assert hall.spy_of_the_month == Champion(name="Аня", value=2, total=3)


async def test_the_spy_of_the_month_forgets_older_games(
    db_session: AsyncSession, word: Word
) -> None:
    await spy_games(db_session, word, wins=3, losses=0, ago=timedelta(days=60))

    hall = await StatsRepository(db_session).hall_of_fame(CHAT_ID, NOW)

    assert hall.spy_of_the_month is None
    assert hall.best_detective is None


async def test_the_best_detective_remembers_everything(
    db_session: AsyncSession, word: Word
) -> None:
    for index in range(3):
        await play(
            db_session,
            word,
            Seat(1, "Аня", is_spy=True),
            Seat(2, "Борис"),
            winner=Winner.CIVILIANS,
            ago=timedelta(days=100 + index),
        )

    hall = await StatsRepository(db_session).hall_of_fame(CHAT_ID, NOW)

    assert hall.best_detective == Champion(name="Борис", value=3, total=3)


async def test_equal_rates_are_broken_by_the_longer_record(
    db_session: AsyncSession, word: Word
) -> None:
    for _index in range(4):
        await play(db_session, word, Seat(1, "Аня"), Seat(2, "Борис", is_spy=True))
    await play(db_session, word, Seat(3, "Вера"), Seat(4, "Галя", is_spy=True))
    await play(db_session, word, Seat(3, "Вера"), Seat(4, "Галя", is_spy=True))
    await play(db_session, word, Seat(3, "Вера"), Seat(4, "Галя", is_spy=True))

    hall = await StatsRepository(db_session).hall_of_fame(CHAT_ID, NOW)

    assert hall.best_detective == Champion(name="Аня", value=4, total=4)


async def test_one_fall_is_not_enough_to_be_the_first_victim(
    db_session: AsyncSession, word: Word
) -> None:
    await play(db_session, word, Seat(1, "Аня", out_order=1), Seat(2, "Борис"))

    hall = await StatsRepository(db_session).hall_of_fame(CHAT_ID, NOW)

    assert hall.first_victim is None


async def test_the_first_victim_is_the_one_who_falls_first_most_often(
    db_session: AsyncSession, word: Word
) -> None:
    await play(db_session, word, Seat(1, "Аня", out_order=1), Seat(2, "Борис", out_order=2))
    await play(db_session, word, Seat(1, "Аня", out_order=1), Seat(2, "Борис", out_order=2))

    hall = await StatsRepository(db_session).hall_of_fame(CHAT_ID, NOW)

    assert hall.first_victim == Champion(name="Аня", value=2)


async def test_a_single_win_is_not_a_streak(db_session: AsyncSession, word: Word) -> None:
    await play(db_session, word, Seat(1, "Аня"), Seat(2, "Борис", is_spy=True))

    hall = await StatsRepository(db_session).hall_of_fame(CHAT_ID, NOW)

    assert hall.longest_streak is None


async def test_the_longest_streak_wins_the_line(db_session: AsyncSession, word: Word) -> None:
    await play(
        db_session, word, Seat(1, "Аня"), Seat(2, "Борис", is_spy=True), ago=timedelta(days=2)
    )
    await play(
        db_session, word, Seat(1, "Аня"), Seat(2, "Борис", is_spy=True), ago=timedelta(days=1)
    )

    hall = await StatsRepository(db_session).hall_of_fame(CHAT_ID, NOW)

    assert hall.longest_streak == Champion(name="Аня", value=2)


async def test_the_hall_calls_a_player_by_their_latest_name(
    db_session: AsyncSession, word: Word
) -> None:
    await play(
        db_session, word, Seat(1, "Аня", out_order=1), Seat(2, "Борис"), ago=timedelta(days=5)
    )
    await play(
        db_session, word, Seat(1, "Анна", out_order=1), Seat(2, "Борис"), ago=timedelta(days=1)
    )

    hall = await StatsRepository(db_session).hall_of_fame(CHAT_ID, NOW)

    assert hall.first_victim == Champion(name="Анна", value=2)


async def test_a_deleted_game_takes_its_player_rows_with_it(
    db_session: AsyncSession, word: Word
) -> None:
    await play(db_session, word, Seat(1, "Аня"), Seat(2, "Борис"))
    await db_session.execute(delete(GameSessionLog).where(GameSessionLog.chat_id == CHAT_ID))

    assert await StatsRepository(db_session).player_profile(CHAT_ID, 1) is None


async def test_the_repository_is_a_source_of_statistics(db_session: AsyncSession) -> None:
    source: StatsSource = StatsRepository(db_session)

    assert (await source.chat_totals(CHAT_ID)).games == 0
