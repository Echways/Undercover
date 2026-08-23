from typing import Final

from discussion_harness import (
    NAMES,
    SESSION_ID,
    SPY_INDEX,
    Table,
    group_voting,
    log,
    make_state,
    repainted,
    repainted_texts,
    table,
    voting,
    words,
)
from undercover.bot.routers.discussion import start_discussion
from undercover.game.models import EliminationBallot, GameStatus, Ruleset, Winner
from undercover.texts import Buttons, Errors, Vote

__all__ = ["log", "table", "words"]

GROUP_IDS: Final = (11, 22, 33, 44)
SPY_NAME: Final = NAMES[SPY_INDEX]
CIVILIANS: Final = tuple(name for index, name in enumerate(NAMES) if index != SPY_INDEX)


async def test_the_screen_offers_every_living_player(table: Table) -> None:
    state = await voting(table)

    assert set(table.card.texts) == {*NAMES, Buttons.BACK_TO_TALK}
    assert state.ballot is not None
    assert state.ballot.options == [0, 1, 2, 3]


async def test_the_hot_seat_screen_asks_the_host_for_the_result(table: Table) -> None:
    await voting(table)

    assert Vote.HOT_SEAT_PROMPT in table.card.caption


async def test_the_group_screen_counts_the_votes_it_waits_for(table: Table) -> None:
    await group_voting(table, GROUP_IDS)

    assert Vote.PROGRESS.format(given=0, total=4) in table.card.caption


async def test_the_host_alone_votes_a_player_out_in_hot_seat(table: Table) -> None:
    await voting(table)

    await table.press(SPY_NAME)

    assert table.games.stored.players[SPY_INDEX].is_out
    assert Vote.VERDICT_SPY.format(name=SPY_NAME) in table.card.caption


async def test_a_civilian_who_leaves_is_named_a_civilian(table: Table) -> None:
    await voting(table)

    await table.press(CIVILIANS[0])

    assert Vote.VERDICT_CIVILIAN.format(name=CIVILIANS[0]) in table.card.caption


async def test_the_last_spy_leaving_wins_the_game_for_the_civilians(table: Table) -> None:
    await voting(table)

    await table.press(SPY_NAME)

    stored = table.games.stored
    assert stored.status is GameStatus.FINISHED
    assert stored.winner is Winner.CIVILIANS
    assert Vote.CIVILIANS_WIN in table.card.caption
    assert Buttons.SHOW_RESULT in table.card.texts


async def test_the_spies_win_when_they_draw_level(table: Table) -> None:
    state = await voting(table)
    state.players[0].is_out = True
    await table.games.save(state)

    await table.press(CIVILIANS[1])

    stored = table.games.stored
    assert stored.status is GameStatus.FINISHED
    assert stored.winner is Winner.SPIES
    assert Vote.SPIES_WIN in table.card.caption


async def test_a_game_that_goes_on_offers_another_round(table: Table) -> None:
    await voting(table)

    await table.press(CIVILIANS[0])

    stored = table.games.stored
    assert stored.status is GameStatus.VOTING
    assert stored.winner is None
    assert stored.ballot is None
    assert Buttons.CONTINUE_TALK in table.card.texts


async def test_continuing_opens_the_next_round_with_the_living(table: Table) -> None:
    await voting(table)
    await table.press(CIVILIANS[0])

    await table.press(Buttons.CONTINUE_TALK)

    stored = table.games.stored
    assert stored.status is GameStatus.DISCUSSION
    assert stored.discussion_round == 2
    assert len(stored.discussion_order) == len(NAMES) - 1
    assert all(not stored.players[index].is_out for index in stored.discussion_order)


async def test_a_won_game_reaches_the_journal_with_its_winner(table: Table) -> None:
    await voting(table)

    await table.press(SPY_NAME)

    (recorded,) = table.log.states
    assert recorded.winner is Winner.CIVILIANS


async def test_a_game_that_goes_on_is_not_in_the_journal_yet(table: Table) -> None:
    await voting(table)

    await table.press(CIVILIANS[0])

    assert table.log.states == []


async def test_a_group_waits_for_the_last_vote_before_anyone_leaves(table: Table) -> None:
    await group_voting(table, GROUP_IDS)
    data = table.card.callback_data(SPY_NAME)

    for voter_id in GROUP_IDS[:3]:
        await table.tap(data, user_id=voter_id)

    assert not table.games.stored.players[SPY_INDEX].is_out
    assert Vote.PROGRESS.format(given=3, total=4) in (repainted(table).caption or "")


async def test_a_group_sends_out_the_player_the_majority_picked(table: Table) -> None:
    await group_voting(table, GROUP_IDS)
    spy = table.card.callback_data(SPY_NAME)
    other = table.card.callback_data(CIVILIANS[0])

    await table.tap(spy, user_id=11)
    await table.tap(spy, user_id=22)
    await table.tap(spy, user_id=33)
    await table.tap(other, user_id=44)

    assert table.games.stored.players[SPY_INDEX].is_out


async def test_the_verdict_shows_the_group_how_the_votes_fell(table: Table) -> None:
    await group_voting(table, GROUP_IDS)
    spy = table.card.callback_data(SPY_NAME)

    for voter_id in GROUP_IDS:
        await table.tap(spy, user_id=voter_id)

    assert Vote.TALLY_LINE.format(name=SPY_NAME, votes=4) in table.card.caption


async def test_nobody_votes_twice(table: Table) -> None:
    await group_voting(table, GROUP_IDS)
    data = table.card.callback_data(SPY_NAME)

    await table.tap(data, user_id=11)
    await table.tap(data, user_id=11)

    assert Vote.ALREADY_VOTED in table.alerts


async def test_an_eliminated_player_is_told_they_no_longer_vote(table: Table) -> None:
    state = await group_voting(table, GROUP_IDS)
    state.players[0].is_out = True
    await table.games.save(state)

    await table.tap(table.card.callback_data(SPY_NAME), user_id=11)

    assert Vote.IS_OUT in table.alerts


async def test_a_stranger_gets_no_vote(table: Table) -> None:
    await group_voting(table, GROUP_IDS)

    await table.tap(table.card.callback_data(SPY_NAME), user_id=999)

    assert Errors.NOT_HOST in table.alerts


async def test_a_tie_sends_only_the_leaders_to_a_second_ballot(table: Table) -> None:
    await group_voting(table, GROUP_IDS)
    one = table.card.callback_data(CIVILIANS[0])
    two = table.card.callback_data(CIVILIANS[1])

    await table.tap(one, user_id=11)
    await table.tap(one, user_id=22)
    await table.tap(two, user_id=33)
    await table.tap(two, user_id=44)

    ballot = table.games.stored.ballot
    assert isinstance(ballot, EliminationBallot)
    assert ballot.revote
    assert ballot.votes == {}
    assert Vote.TIE in table.alerts
    assert repainted_texts(table) == {CIVILIANS[0], CIVILIANS[1], Buttons.BACK_TO_TALK}


async def test_a_second_tie_sends_nobody_out_and_opens_a_new_round(table: Table) -> None:
    await group_voting(table, GROUP_IDS)
    one = table.card.callback_data(CIVILIANS[0])
    two = table.card.callback_data(CIVILIANS[1])

    for _ in range(2):
        await table.tap(one, user_id=11)
        await table.tap(one, user_id=22)
        await table.tap(two, user_id=33)
        await table.tap(two, user_id=44)

    stored = table.games.stored
    assert all(not player.is_out for player in stored.players)
    assert stored.status is GameStatus.DISCUSSION
    assert Vote.NO_ELIMINATION in table.alerts


async def test_the_host_can_call_the_table_back_to_the_discussion(table: Table) -> None:
    await voting(table)

    await table.press(Buttons.BACK_TO_TALK)

    stored = table.games.stored
    assert stored.status is GameStatus.DISCUSSION
    assert stored.ballot is None
    assert all(not player.is_out for player in stored.players)


async def test_only_the_host_calls_the_table_back(table: Table) -> None:
    await group_voting(table, GROUP_IDS)

    await table.tap(table.card.callback_data(Buttons.BACK_TO_TALK), user_id=22)

    assert Errors.NOT_HOST in table.alerts
    assert table.games.stored.status is GameStatus.VOTING


async def test_only_the_host_moves_the_game_on_after_a_verdict(table: Table) -> None:
    await group_voting(table, GROUP_IDS)
    victim = table.card.callback_data(CIVILIANS[0])
    for voter_id in GROUP_IDS:
        await table.tap(victim, user_id=voter_id)

    await table.tap(table.card.callback_data(Buttons.CONTINUE_TALK), user_id=22)

    assert Errors.NOT_HOST in table.alerts
    assert table.games.stored.status is GameStatus.VOTING


async def test_the_voting_screen_silences_the_clock(table: Table) -> None:
    await voting(table, turn_seconds=60)

    assert table.keeper.clock.running == frozenset()


async def test_voting_buttons_are_dead_once_the_game_is_over(table: Table) -> None:
    await voting(table)
    data = table.card.callback_data(SPY_NAME)
    await table.tap(data)

    await table.tap(data)

    assert Vote.WRONG_PHASE in table.alerts


async def speak_out_the_round(table: Table) -> None:
    for _ in range(len(table.games.stored.discussion_order) - 1):
        await table.press(Buttons.NEXT_SPEAKER)


async def test_a_whole_game_runs_from_the_first_round_to_a_victory(table: Table) -> None:
    state = make_state()
    await table.games.save(state)
    await start_discussion(table.bot, table.games, state, table.keeper)

    await speak_out_the_round(table)
    await table.press(Buttons.GO_TO_VOTE)
    await table.press(CIVILIANS[0])

    after_first = table.games.stored
    assert after_first.players[NAMES.index(CIVILIANS[0])].is_out
    assert after_first.winner is None

    await table.press(Buttons.CONTINUE_TALK)
    assert len(table.games.stored.discussion_order) == 3

    await speak_out_the_round(table)
    await table.press(Buttons.GO_TO_VOTE)
    await table.press(SPY_NAME)

    won = table.games.stored
    assert won.status is GameStatus.FINISHED
    assert won.winner is Winner.CIVILIANS

    await table.press(Buttons.SHOW_RESULT)

    assert SPY_NAME in table.card.caption
    assert Buttons.PLAY_AGAIN in table.card.texts
    assert table.games.stored.session_id == SESSION_ID


async def test_a_first_shot_into_a_civilian_ends_a_sudden_death_game(table: Table) -> None:
    await voting(table, ruleset=Ruleset.SUDDEN_DEATH)

    await table.press(CIVILIANS[0])

    stored = table.games.stored
    assert stored.status is GameStatus.FINISHED
    assert stored.winner is Winner.SPIES
    assert Vote.SPIES_WIN_MISFIRE in table.card.caption
    assert Buttons.SHOW_RESULT in table.card.texts


async def test_a_first_shot_into_the_spy_still_wins_a_sudden_death_game(table: Table) -> None:
    await voting(table, ruleset=Ruleset.SUDDEN_DEATH)

    await table.press(SPY_NAME)

    stored = table.games.stored
    assert stored.winner is Winner.CIVILIANS
    assert Vote.CIVILIANS_WIN in table.card.caption


async def test_a_sudden_death_win_reaches_the_journal(table: Table) -> None:
    await voting(table, ruleset=Ruleset.SUDDEN_DEATH)

    await table.press(CIVILIANS[0])

    assert [state.winner for state in table.log.states] == [Winner.SPIES]


async def test_the_final_screen_repeats_why_the_spies_took_it(table: Table) -> None:
    await voting(table, ruleset=Ruleset.SUDDEN_DEATH)
    await table.press(CIVILIANS[0])

    await table.press(Buttons.SHOW_RESULT)

    assert Vote.SPIES_WIN_MISFIRE in table.card.caption


async def test_a_game_finished_by_the_vote_gets_a_case_number(table: Table) -> None:
    await voting(table)

    await table.press(SPY_NAME)

    stored = table.games.stored
    assert stored.case_number == 1
    assert stored.finished_at is not None
