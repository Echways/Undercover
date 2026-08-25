from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendPhoto

from discussion_harness import (
    NAMES,
    SESSION_ID,
    Table,
    all_spoken,
    finished,
    log,
    table,
    talking,
    words,
)
from fake_bot import CHAT_ID
from fake_words import WORD, pizza
from undercover.bot.callbacks import FinalAction, FinalCB
from undercover.game.models import GameStatus, Ruleset, Seating, Winner
from undercover.texts import Buttons, Discussion, Errors, Lobby, Vote
from undercover.texts import Setup as SetupTexts

__all__ = ["log", "table", "words"]


async def test_the_hunt_still_ends_the_game_after_another_round(table: Table) -> None:
    await all_spoken(table)
    await table.press(Buttons.ANOTHER_ROUND)

    await table.press(Buttons.SHOW_SPIES)

    assert table.games.stored.status is GameStatus.FINISHED


async def test_the_next_game_counts_rounds_from_the_first(table: Table) -> None:
    await all_spoken(table)
    await table.press(Buttons.ANOTHER_ROUND)
    await table.press(Buttons.SHOW_SPIES)

    await table.press(Buttons.PLAY_AGAIN)

    assert table.games.stored.discussion_round == 1


async def test_the_final_screen_names_every_spy_and_the_word(table: Table) -> None:
    await talking(table, names=("Аня", "Борис", "Вера", "Галя", "Дима", "Егор"), spies=(1, 4))

    await table.press(Buttons.SHOW_SPIES)

    assert table.card.caption == Discussion.FINAL_CAPTION.format(
        title=Discussion.SPY_TITLE_MANY, spies="Борис, Дима", word=WORD
    )


async def test_the_finished_game_waits_for_the_next_decision(table: Table) -> None:
    state = await finished(table)

    assert state.status is GameStatus.FINISHED
    assert await table.games.load(SESSION_ID) is not None


async def test_the_finished_game_goes_to_the_journal(table: Table) -> None:
    state = await finished(table, spies=(1, 2))

    (recorded,) = table.log.states
    assert recorded.session_id == state.session_id
    assert recorded.status is GameStatus.FINISHED
    assert [player.is_spy for player in recorded.players] == [False, True, True, False]


async def test_a_broken_journal_does_not_break_the_final_screen(table: Table) -> None:
    table.log.failure = RuntimeError("нет связи с базой")

    await talking(table)
    await table.press(Buttons.SHOW_SPIES)

    assert table.card.texts == (Buttons.PLAY_AGAIN, Buttons.RESTART)
    assert table.games.stored.status is GameStatus.FINISHED
    assert table.alerts[-1] is None


async def test_discussion_buttons_are_dead_after_the_game_is_over(table: Table) -> None:
    await talking(table)
    stale = table.card.callback_data(Buttons.NEXT_PLAYER)
    await table.press(Buttons.SHOW_SPIES)

    await table.tap(stale)

    assert table.alerts[-1] == Discussion.WRONG_PHASE


async def test_final_buttons_are_dead_while_the_game_is_on(table: Table) -> None:
    await talking(table)

    await table.tap(FinalCB(action=FinalAction.AGAIN, session_id=SESSION_ID).pack())

    assert table.alerts[-1] == Discussion.GAME_IS_ON
    assert table.games.stored.status is GameStatus.DISCUSSION


async def test_an_unknown_session_is_reported(table: Table) -> None:
    await table.tap(FinalCB(action=FinalAction.AGAIN, session_id="нет-такой").pack())

    assert table.alerts == [Errors.SESSION_NOT_FOUND]
    assert not table.cards


async def test_play_again_keeps_the_roster_and_deals_a_fresh_game(table: Table) -> None:
    old = await finished(table)

    await table.press(Buttons.PLAY_AGAIN)

    fresh = table.games.stored
    assert fresh.session_id != old.session_id, "это новая партия, а не продолжение старой"
    assert [player.name for player in fresh.players] == list(NAMES)
    assert [player.order_index for player in fresh.players] == list(range(len(NAMES)))
    assert sum(player.is_spy for player in fresh.players) == 1
    assert not any(player.has_viewed for player in fresh.players)
    assert fresh.status is GameStatus.REVEAL
    assert fresh.reveal_cursor == 0
    assert fresh.discussion_order == []


async def test_play_again_keeps_the_ruleset_the_table_agreed_on(table: Table) -> None:
    await finished(table, ruleset=Ruleset.SUDDEN_DEATH)

    await table.press(Buttons.PLAY_AGAIN)

    assert table.games.stored.ruleset is Ruleset.SUDDEN_DEATH


async def test_play_again_keeps_the_chosen_categories(table: Table) -> None:
    await finished(table, category_ids=[2, 5])

    await table.press(Buttons.PLAY_AGAIN)

    assert table.games.stored.category_ids == [2, 5]
    assert table.words.asked_categories[-1] in (2, 5)


async def test_play_again_without_words_in_the_chosen_categories_is_explained(
    table: Table,
) -> None:
    old = await finished(table, category_ids=[2])
    table.words.empty_categories = frozenset({2})

    await table.press(Buttons.PLAY_AGAIN)

    assert table.alerts[-1] == Errors.EMPTY_CATEGORIES
    assert table.games.stored.session_id == old.session_id


async def test_play_again_forgets_the_finished_game(table: Table) -> None:
    old = await finished(table)

    await table.press(Buttons.PLAY_AGAIN)

    active = await table.games.load_active(CHAT_ID)

    assert await table.games.load(old.session_id) is None
    assert active is not None
    assert active.session_id == table.games.stored.session_id


async def test_play_again_reuses_the_cached_hidden_cards(table: Table) -> None:
    await talking(table)
    cached = table.games.stored
    for player in cached.players:
        player.card_file_id = f"cached-{player.order_index}"
    await table.games.save(cached)
    await table.press(Buttons.SHOW_SPIES)

    await table.press(Buttons.PLAY_AGAIN)

    assert table.card.photo == "cached-0"
    assert [player.card_file_id for player in table.games.stored.players] == [
        f"cached-{index}" for index in range(len(NAMES))
    ]


async def test_play_again_continues_in_the_same_message(table: Table) -> None:
    await finished(table)
    sent = len(table.session.calls(SendPhoto))

    await table.press(Buttons.PLAY_AGAIN)

    assert len(table.session.calls(SendPhoto)) == sent, "экран партии остался тем же сообщением"


async def test_play_again_without_a_word_keeps_the_finished_game(table: Table) -> None:
    old = await finished(table)
    table.words.word = None

    await table.press(Buttons.PLAY_AGAIN)

    assert table.alerts[-1] == Errors.EMPTY_CATALOG
    assert table.games.stored.session_id == old.session_id

    table.words.word = pizza()
    await table.press(Buttons.PLAY_AGAIN)

    assert table.games.stored.session_id != old.session_id


async def test_new_game_wipes_the_session_and_opens_the_setup(table: Table) -> None:
    old = await finished(table)

    await table.press(Buttons.RESTART)

    assert await table.games.load(old.session_id) is None
    assert SetupTexts.ASK_PLAYERS_COUNT in (table.window.text or "")


async def test_new_game_asks_for_the_roster_from_scratch(table: Table) -> None:
    await finished(table)
    await table.press(Buttons.RESTART)

    await table.send("2")
    await table.send("Зина")
    await table.send("Игорь")
    await table.click(Buttons.PLAY)

    assert [player.name for player in table.games.stored.players] == ["Зина", "Игорь"]


async def test_the_final_screen_silences_the_clock(table: Table) -> None:
    await talking(table, seating=Seating.GROUP, turn_seconds=60)
    assert table.keeper.clock.running

    await table.press(Buttons.SHOW_SPIES)

    assert table.keeper.clock.running == frozenset()


async def test_a_new_roster_silences_the_clock(table: Table) -> None:
    await finished(table, seating=Seating.GROUP, turn_seconds=60)

    await table.press(Buttons.RESTART)

    assert table.keeper.clock.running == frozenset()


async def test_another_group_game_deals_roles_in_private_and_opens_the_first_turn(
    table: Table,
) -> None:
    old = await finished(table, seating=Seating.GROUP, ids=(10, 20, 30, 40), turn_seconds=60)
    sent_before = len(table.session.calls(SendPhoto))

    await table.press(Buttons.PLAY_AGAIN)

    fresh = table.games.stored
    assert fresh.session_id != old.session_id
    assert fresh.seating is Seating.GROUP
    assert fresh.turn_seconds == 60
    assert fresh.status is GameStatus.DISCUSSION
    assert [player.user_id for player in fresh.players] == [10, 20, 30, 40]

    dealt = [call.chat_id for call in table.session.calls(SendPhoto)[sent_before:]]
    assert sorted(dealt[:-1]) == [10, 20, 30, 40]
    assert dealt[-1] == CHAT_ID


async def test_an_undelivered_role_keeps_the_finished_group_game(table: Table) -> None:
    old = await finished(table, seating=Seating.GROUP, ids=(10, 20, 30, 40), turn_seconds=60)
    table.session.failures[SendPhoto] = TelegramForbiddenError(
        method=SendPhoto(chat_id=10, photo="x"), message="bot was blocked by the user"
    )

    await table.press(Buttons.PLAY_AGAIN)

    assert table.games.stored.session_id == old.session_id
    assert table.alerts[-1] == Lobby.DELIVERY_FAILED


async def test_only_the_host_uncovers_the_spies(table: Table) -> None:
    state = await talking(table, ids=(11, 22, 33, 44), seating=Seating.GROUP)
    silent = state.players[state.discussion_order[-1]]
    assert silent.user_id is not None

    await table.tap(table.card.callback_data(Buttons.SHOW_SPIES), user_id=silent.user_id)

    assert Discussion.NOT_YOUR_TURN in table.alerts
    assert table.games.stored.status is GameStatus.DISCUSSION


async def test_an_early_exit_ends_the_game_without_a_winner(table: Table) -> None:
    await finished(table)

    stored = table.games.stored
    assert stored.status is GameStatus.FINISHED
    assert stored.winner is None
    assert Vote.CIVILIANS_WIN not in table.card.caption
    assert Vote.SPIES_WIN not in table.card.caption


async def test_the_result_screen_says_who_won(table: Table) -> None:
    state = await talking(table)
    state.status = GameStatus.FINISHED
    state.winner = Winner.SPIES
    await table.games.save(state)

    await table.tap(FinalCB(action=FinalAction.RESULT, session_id=SESSION_ID).pack())

    assert Vote.SPIES_WIN in table.card.caption
    assert WORD in table.card.caption


async def test_the_result_screen_still_offers_the_next_game(table: Table) -> None:
    state = await talking(table)
    state.status = GameStatus.FINISHED
    state.winner = Winner.CIVILIANS
    await table.games.save(state)

    await table.tap(FinalCB(action=FinalAction.RESULT, session_id=SESSION_ID).pack())

    assert Buttons.PLAY_AGAIN in table.card.texts
    assert Buttons.RESTART in table.card.texts


async def test_the_result_screen_is_dead_while_the_game_is_on(table: Table) -> None:
    await talking(table)

    await table.tap(FinalCB(action=FinalAction.RESULT, session_id=SESSION_ID).pack())

    assert Discussion.GAME_IS_ON in table.alerts


async def test_the_case_number_comes_from_the_journal(table: Table) -> None:
    await finished(table)

    assert table.games.stored.case_number == 1


async def test_the_game_is_stamped_with_the_moment_it_ended(table: Table) -> None:
    await finished(table)

    assert table.games.stored.finished_at is not None


async def test_the_case_number_survives_a_second_look(table: Table) -> None:
    await finished(table)
    stamped = table.games.stored.finished_at

    await table.tap(FinalCB(action=FinalAction.RESULT, session_id=SESSION_ID).pack())

    assert table.games.stored.case_number == 1
    assert table.games.stored.finished_at == stamped


async def test_a_broken_journal_leaves_the_case_without_a_number(table: Table) -> None:
    table.log.failure = RuntimeError("журнал недоступен")

    await finished(table)

    assert table.games.stored.case_number is None
    assert table.games.stored.status is GameStatus.FINISHED
