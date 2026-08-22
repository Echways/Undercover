import asyncio

from aiogram.methods import EditMessageCaption, EditMessageMedia, SendPhoto

from discussion_harness import (
    NAMES,
    OUTSIDER_ID,
    SESSION_ID,
    Table,
    all_spoken,
    finished,
    log,
    make_state,
    spoken_names,
    table,
    talking,
    words,
)
from fake_bot import CHAT_ID, HOST_ID
from fake_words import WORD, pizza
from undercover.bot.routers.discussion import TalkAction, TalkCB, expiry_handler
from undercover.bot.turn_clock import Turn
from undercover.game.models import GameMode, GameStatus
from undercover.texts import BAR_EMPTY, Buttons, Discussion, Errors, Timer, countdown_line

__all__ = ["log", "table", "words"]


async def test_the_whole_game_from_setup_to_the_final_screen(table: Table) -> None:
    await table.send("/start")
    await table.send("2")
    await table.send("1")
    await table.send("Аня")
    await table.send("Борис")
    await table.click(Buttons.PLAY)

    dealt = table.games.stored
    assert [player.name for player in dealt.players] == ["Аня", "Борис"]
    assert dealt.status is GameStatus.REVEAL

    await table.press(Buttons.SHOW_CARD)
    await table.press(Buttons.NEXT_PLAYER)
    await table.press(Buttons.SHOW_CARD)
    await table.press(Buttons.START_DISCUSSION)

    talk = table.games.stored
    assert talk.status is GameStatus.DISCUSSION
    assert sorted(talk.discussion_order) == [0, 1], "высказываются все и по разу"
    assert talk.discussion_cursor == 0
    opening = table.card

    assert opening.texts == (Buttons.NEXT_SPEAKER, Buttons.SHOW_SPIES)

    await table.press(Buttons.NEXT_SPEAKER)

    assert table.games.stored.discussion_cursor == 1
    assert table.card.texts == (
        Buttons.ANOTHER_ROUND,
        Buttons.SHOW_SPIES,
    ), "все высказались — остаётся пойти на второй круг или искать шпиона"

    await table.press(Buttons.SHOW_SPIES)

    spy = next(player.name for player in talk.players if player.is_spy)
    final = table.card

    assert final.caption == Discussion.FINAL_CAPTION.format(
        title=Discussion.SPY_TITLE_ONE, spies=spy, word=WORD
    )
    assert final.texts == (Buttons.PLAY_AGAIN, Buttons.NEW_GAME)
    assert table.games.stored.status is GameStatus.FINISHED
    assert table.alerts == [None] * 6, "ни одно нажатие не отклонено"
    assert len(table.session.calls(SendPhoto)) == 1, "вся партия прожила в одном сообщении"

    (recorded,) = table.log.states
    assert (recorded.chat_id, recorded.host_user_id) == (CHAT_ID, HOST_ID)
    assert (len(recorded.players), recorded.word_id) == (2, pizza().id)


async def test_discussion_order_is_a_permutation_of_the_roster(table: Table) -> None:
    state = await talking(table)

    assert sorted(state.discussion_order) == list(range(len(NAMES)))
    assert state.discussion_cursor == 0


async def test_every_player_speaks_once_and_then_the_hunt_begins(table: Table) -> None:
    state = await talking(table)

    for cursor in range(len(NAMES) - 1):
        speaker = NAMES[state.discussion_order[cursor]]
        assert table.card.caption == Discussion.TALK_CAPTION.format(
            position=cursor + 1, total=len(NAMES), name=speaker
        )
        assert table.card.texts == (Buttons.NEXT_SPEAKER, Buttons.SHOW_SPIES)
        await table.press(Buttons.NEXT_SPEAKER)

    last = NAMES[state.discussion_order[-1]]
    assert table.card.caption == Discussion.LAST_TALK_CAPTION.format(name=last)
    assert table.card.texts == (Buttons.ANOTHER_ROUND, Buttons.SHOW_SPIES)
    assert sorted(spoken_names(table)) == sorted(NAMES)


async def test_a_stale_button_does_not_skip_a_speaker(table: Table) -> None:
    await talking(table)
    stale = table.card.callback_data(Buttons.NEXT_SPEAKER)
    await table.press(Buttons.NEXT_SPEAKER)
    shown = len(table.cards)

    await table.tap(stale)

    assert table.alerts[-1] == Errors.STALE_TURN
    assert table.games.stored.discussion_cursor == 1
    assert len(table.cards) == shown


async def test_an_outsider_does_not_move_the_discussion(table: Table) -> None:
    await talking(table)

    await table.press(Buttons.NEXT_SPEAKER, user_id=OUTSIDER_ID)

    assert table.alerts[-1] == Errors.NOT_HOST
    assert table.games.stored.discussion_cursor == 0


async def test_there_is_no_speaker_after_the_last_one(table: Table) -> None:
    state = await talking(table)
    last = len(NAMES) - 1

    await table.tap(
        TalkCB(action=TalkAction.NEXT, session_id=SESSION_ID, cursor=state.discussion_cursor).pack()
    )
    for _ in range(1, last):
        await table.press(Buttons.NEXT_SPEAKER)

    await table.tap(TalkCB(action=TalkAction.NEXT, session_id=SESSION_ID, cursor=last).pack())

    assert table.alerts[-1] == Discussion.ALL_SPOKE
    assert table.games.stored.discussion_cursor == last


async def test_a_broken_speaking_order_is_reported(table: Table) -> None:
    await table.games.save(make_state(discussion_order=[0, 99, 1], discussion_cursor=0))

    await table.tap(TalkCB(action=TalkAction.NEXT, session_id=SESSION_ID, cursor=0).pack())

    assert table.alerts == [Errors.BROKEN_SESSION]
    assert not table.cards


async def test_another_round_waits_until_everyone_has_spoken(table: Table) -> None:
    state = await talking(table)

    for _ in range(len(state.discussion_order) - 1):
        assert Buttons.ANOTHER_ROUND not in table.card.texts
        await table.press(Buttons.NEXT_SPEAKER)

    assert table.card.texts == (Buttons.ANOTHER_ROUND, Buttons.SHOW_SPIES)


async def test_another_round_starts_the_circle_over_in_the_same_order(table: Table) -> None:
    state = await all_spoken(table)

    await table.press(Buttons.ANOTHER_ROUND)

    repeated = table.games.stored
    assert repeated.discussion_order == state.discussion_order
    assert repeated.discussion_cursor == 0
    assert repeated.discussion_round == 2
    assert repeated.status is GameStatus.DISCUSSION


async def test_the_first_round_caption_stays_free_of_numbering(table: Table) -> None:
    state = await talking(table)

    assert state.discussion_round == 1
    assert table.card.caption == Discussion.TALK_CAPTION.format(
        position=1, total=len(NAMES), name=NAMES[state.discussion_order[0]]
    )


async def test_a_later_round_is_numbered_in_the_caption(table: Table) -> None:
    state = await all_spoken(table)

    await table.press(Buttons.ANOTHER_ROUND)

    assert table.card.caption == Discussion.ROUND_PREFIX.format(
        round=2
    ) + Discussion.TALK_CAPTION.format(
        position=1, total=len(NAMES), name=NAMES[state.discussion_order[0]]
    )


async def test_a_later_round_numbers_its_last_speaker_too(table: Table) -> None:
    state = await all_spoken(table)

    await table.press(Buttons.ANOTHER_ROUND)
    for _ in range(len(NAMES) - 1):
        await table.press(Buttons.NEXT_SPEAKER)

    assert table.card.caption == Discussion.ROUND_PREFIX.format(
        round=2
    ) + Discussion.LAST_TALK_CAPTION.format(name=NAMES[state.discussion_order[-1]])


async def test_another_round_does_not_cut_the_current_one_short(table: Table) -> None:
    await talking(table)

    await table.tap(TalkCB(action=TalkAction.ROUND, session_id=SESSION_ID, cursor=0).pack())

    assert table.alerts[-1] == Errors.STALE_TURN
    assert table.games.stored.discussion_round == 1
    assert table.games.stored.discussion_cursor == 0


async def test_a_broken_order_does_not_open_another_round(table: Table) -> None:
    await table.games.save(
        make_state(names=("Аня", "Борис"), discussion_order=[99, 0], discussion_cursor=1)
    )

    await table.tap(TalkCB(action=TalkAction.ROUND, session_id=SESSION_ID, cursor=1).pack())

    assert table.alerts == [Errors.BROKEN_SESSION]
    assert not table.cards
    assert table.games.stored.discussion_round == 1


async def test_a_stale_another_round_button_does_not_restart_the_circle(table: Table) -> None:
    await all_spoken(table)
    stale = table.card.callback_data(Buttons.ANOTHER_ROUND)
    await table.press(Buttons.ANOTHER_ROUND)
    shown = len(table.cards)

    await table.tap(stale)

    assert table.alerts[-1] == Errors.STALE_TURN
    assert table.games.stored.discussion_round == 2
    assert len(table.cards) == shown


async def test_an_outsider_does_not_start_another_round(table: Table) -> None:
    await all_spoken(table)

    await table.press(Buttons.ANOTHER_ROUND, user_id=OUTSIDER_ID)

    assert table.alerts[-1] == Errors.NOT_HOST
    assert table.games.stored.discussion_round == 1


async def test_a_group_game_gives_every_speaker_their_own_message(table: Table) -> None:
    await talking(table, mode=GameMode.GROUP)
    opened = len(table.session.calls(SendPhoto))

    await table.press(Buttons.NEXT_SPEAKER)

    assert len(table.session.calls(SendPhoto)) == opened + 1
    assert not table.session.calls(EditMessageMedia)


async def test_the_finished_group_turn_is_frozen_without_buttons(table: Table) -> None:
    state = await talking(table, mode=GameMode.GROUP)
    spoke = state.players[state.discussion_order[0]].name

    await table.press(Buttons.NEXT_SPEAKER)

    (frozen,) = table.session.calls(EditMessageCaption)
    assert frozen.reply_markup is None
    assert spoke in (frozen.caption or "")


async def test_hot_seat_still_lives_in_one_message(table: Table) -> None:
    await talking(table)

    await table.press(Buttons.NEXT_SPEAKER)

    assert not table.session.calls(EditMessageCaption)
    assert table.session.calls(EditMessageMedia)


async def test_the_speaker_may_end_their_own_turn_in_a_group(table: Table) -> None:
    state = await talking(table, mode=GameMode.GROUP, ids=(10, 20, 30, 40))
    speaker = state.players[state.discussion_order[0]]
    assert speaker.user_id is not None

    await table.press(Buttons.NEXT_SPEAKER, user_id=speaker.user_id)

    assert table.games.stored.discussion_cursor == 1


async def test_a_bystander_still_cannot_move_the_turn(table: Table) -> None:
    state = await talking(table, mode=GameMode.GROUP, ids=(10, 20, 30, 40))
    waiting = state.players[state.discussion_order[1]]
    assert waiting.user_id is not None

    await table.press(Buttons.NEXT_SPEAKER, user_id=waiting.user_id)

    assert table.games.stored.discussion_cursor == 0
    assert table.alerts[-1] == Errors.NOT_HOST


async def test_a_new_round_freezes_the_last_turn_before_the_counter_moves(table: Table) -> None:
    await all_spoken(table, mode=GameMode.GROUP)
    frozen_before = len(table.session.calls(EditMessageCaption))

    await table.press(Buttons.ANOTHER_ROUND)

    frozen = table.session.calls(EditMessageCaption)[frozen_before]
    assert Discussion.ROUND_PREFIX.format(round=2) not in (frozen.caption or "")
    assert table.games.stored.discussion_round == 2


async def test_a_timed_group_turn_shows_the_countdown_from_the_first_frame(table: Table) -> None:
    state = await talking(table, mode=GameMode.GROUP, turn_seconds=60)

    assert countdown_line(60, 60) in table.card.caption
    assert state.turn_deadline is not None


async def test_a_hot_seat_turn_carries_no_countdown(table: Table) -> None:
    state = await talking(table)

    assert state.turn_deadline is None
    assert BAR_EMPTY not in table.card.caption


async def test_pressing_next_reports_the_time_the_speaker_took(table: Table) -> None:
    await talking(table, mode=GameMode.GROUP, turn_seconds=60)

    await table.press(Buttons.NEXT_SPEAKER)

    (frozen,) = table.session.calls(EditMessageCaption)
    assert Timer.SPENT.format(seconds=0) in (frozen.caption or "")


async def test_an_expired_turn_moves_on_by_itself(table: Table) -> None:
    state = await talking(table, mode=GameMode.GROUP, turn_seconds=60)
    on_expire = expiry_handler(table.games, table.keeper)

    await on_expire(table.bot, Turn(SESSION_ID, state.discussion_round, state.discussion_cursor))

    assert table.games.stored.discussion_cursor == 1
    (frozen,) = table.session.calls(EditMessageCaption)
    assert Timer.EXPIRED in (frozen.caption or "")
    assert frozen.reply_markup is None


async def test_an_expired_last_turn_keeps_the_round_buttons(table: Table) -> None:
    state = await all_spoken(table, mode=GameMode.GROUP, turn_seconds=60)
    last = state.discussion_cursor
    frozen_before = len(table.session.calls(EditMessageCaption))
    on_expire = expiry_handler(table.games, table.keeper)

    await on_expire(table.bot, Turn(SESSION_ID, state.discussion_round, last))

    frozen = table.session.calls(EditMessageCaption)[frozen_before]
    assert Timer.EXPIRED in (frozen.caption or "")
    assert frozen.reply_markup is not None
    assert Buttons.ANOTHER_ROUND in [
        item.text for row in frozen.reply_markup.inline_keyboard for item in row
    ]
    assert table.games.stored.discussion_cursor == last


async def test_a_stale_tick_is_ignored(table: Table) -> None:
    await talking(table, mode=GameMode.GROUP, turn_seconds=60)
    await table.press(Buttons.NEXT_SPEAKER)
    on_expire = expiry_handler(table.games, table.keeper)

    await on_expire(table.bot, Turn(SESSION_ID, round=1, cursor=0))

    assert table.games.stored.discussion_cursor == 1


async def test_a_tick_of_a_game_that_is_over_changes_nothing(table: Table) -> None:
    state = await finished(table, mode=GameMode.GROUP, turn_seconds=60)
    on_expire = expiry_handler(table.games, table.keeper)

    await on_expire(table.bot, Turn(SESSION_ID, state.discussion_round, state.discussion_cursor))

    assert table.games.stored.status is GameStatus.FINISHED


async def test_a_tick_of_a_forgotten_game_changes_nothing(table: Table) -> None:
    on_expire = expiry_handler(table.games, table.keeper)

    await on_expire(table.bot, Turn("нет-такой", round=1, cursor=0))

    assert table.games.is_empty


async def test_a_button_and_an_expiry_racing_move_the_turn_exactly_once(table: Table) -> None:
    state = await talking(table, mode=GameMode.GROUP, turn_seconds=60)
    on_expire = expiry_handler(table.games, table.keeper)
    opened = len(table.session.calls(SendPhoto))

    await asyncio.gather(
        on_expire(table.bot, Turn(SESSION_ID, state.discussion_round, state.discussion_cursor)),
        table.press(Buttons.NEXT_SPEAKER),
    )

    assert len(table.session.calls(SendPhoto)) == opened + 1
    assert table.games.stored.discussion_cursor == 1


async def test_a_tick_on_a_broken_order_opens_no_turn(table: Table) -> None:
    await table.games.save(
        make_state(
            mode=GameMode.GROUP, turn_seconds=60, discussion_order=[0, 99], discussion_cursor=0
        )
    )
    on_expire = expiry_handler(table.games, table.keeper)

    await on_expire(table.bot, Turn(SESSION_ID, round=1, cursor=0))

    assert table.games.stored.discussion_cursor == 0
    assert not table.cards
