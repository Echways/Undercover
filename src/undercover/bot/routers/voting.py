import asyncio
from collections.abc import Mapping
from itertools import batched

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from undercover.bot.acks import ack
from undercover.bot.boards import board_for
from undercover.bot.callbacks import FinalAction, FinalCB, PickCB, VoteAction, VoteCB
from undercover.bot.cards import card_photo
from undercover.bot.guards import deny_non_host, load_voting
from undercover.bot.keyboards import button, single_button
from undercover.bot.phases import GameLogWriter, PhaseStarter, close_case
from undercover.bot.turn_clock import TurnKeeper
from undercover.game.models import (
    EliminationBallot,
    GameSessionState,
    GameStatus,
    PlayerState,
    Seating,
    Winner,
)
from undercover.game.voting import (
    alive,
    cast_elimination,
    close_ballot,
    eliminate,
    elimination_result,
    misfired,
    open_elimination_ballot,
    outcome,
    turnout,
)
from undercover.media.card_renderer import render_ballot_card, render_verdict_card
from undercover.redis.game_state import GameStateRepository
from undercover.texts import VOTE_REFUSALS, Buttons, Vote, win_line


def create_voting_router(
    keeper: TurnKeeper, start_discussion: PhaseStarter, log_game: GameLogWriter
) -> Router:
    router = Router(name="voting")

    async def next_round(bot: Bot, games: GameStateRepository, state: GameSessionState) -> None:
        state.status = GameStatus.DISCUSSION
        state.discussion_round += 1
        await start_discussion(bot, games, state)

    @router.callback_query(PickCB.filter())
    async def cb_pick(
        callback: CallbackQuery,
        callback_data: PickCB,
        games: GameStateRepository,
        bot: Bot,
    ) -> None:
        async with keeper.locks.held(callback_data.session_id):
            state = await load_voting(callback, callback_data.session_id, games)
            if state is None:
                return

            refusal = cast_elimination(state, callback.from_user.id, callback_data.order_index)
            if refusal is not None:
                await ack(callback, VOTE_REFUSALS[refusal], show_alert=True)
                return

            verdict = elimination_result(state)
            if verdict is None:
                await games.save(state)
                await _repaint(bot, state, _ballot_caption(state))
                await ack(callback)
                return

            if verdict.revote is not None:
                open_elimination_ballot(state, verdict.revote, revote=True)
                await games.save(state)
                await _repaint(bot, state, Vote.TIE)
                await ack(callback, Vote.TIE, show_alert=True)
                return

            if verdict.eliminated is None:
                close_ballot(state)
                await ack(callback, Vote.NO_ELIMINATION, show_alert=True)
                await next_round(bot, games, state)
                return

            await _announce(bot, games, log_game, state, verdict.eliminated, verdict.counts)
            await ack(callback)

    @router.callback_query(VoteCB.filter(F.action == VoteAction.BACK))
    async def cb_back(
        callback: CallbackQuery,
        callback_data: VoteCB,
        games: GameStateRepository,
        bot: Bot,
    ) -> None:
        async with keeper.locks.held(callback_data.session_id):
            state = await load_voting(callback, callback_data.session_id, games)
            if state is None or await deny_non_host(callback, state):
                return

            close_ballot(state)
            await next_round(bot, games, state)
            await ack(callback)

    @router.callback_query(VoteCB.filter(F.action == VoteAction.CONTINUE))
    async def cb_continue(
        callback: CallbackQuery,
        callback_data: VoteCB,
        games: GameStateRepository,
        bot: Bot,
    ) -> None:
        async with keeper.locks.held(callback_data.session_id):
            state = await load_voting(callback, callback_data.session_id, games)
            if state is None or await deny_non_host(callback, state):
                return

            await next_round(bot, games, state)
            await ack(callback)

    return router


async def start_voting(
    bot: Bot, games: GameStateRepository, state: GameSessionState, keeper: TurnKeeper
) -> None:
    keeper.clock.stop(state.session_id)
    state.status = GameStatus.VOTING
    open_elimination_ballot(state, [player.order_index for player in alive(state)])

    image = await asyncio.to_thread(render_ballot_card)
    state.current_message_id = await board_for(state).show(
        bot,
        state,
        card_photo(image, "ballot"),
        _ballot_caption(state),
        _ballot_keyboard(state),
    )
    await games.save(state)


async def _announce(
    bot: Bot,
    games: GameStateRepository,
    log_game: GameLogWriter,
    state: GameSessionState,
    order_index: int,
    counts: Mapping[int, int],
) -> None:
    player = eliminate(state, order_index)
    winner = outcome(state)
    if winner is not None:
        state.status = GameStatus.FINISHED
        state.winner = winner
        await close_case(log_game, state)

    image = await asyncio.to_thread(render_verdict_card, player.name, player.is_spy)
    state.current_message_id = await board_for(state).show(
        bot,
        state,
        card_photo(image, "verdict"),
        _verdict_caption(state, player, counts, winner),
        _verdict_keyboard(state, winner),
    )
    await games.save(state)


async def _repaint(bot: Bot, state: GameSessionState, caption: str) -> None:
    await board_for(state).revise(bot, state, caption, _ballot_keyboard(state))


def _ballot_caption(state: GameSessionState) -> str:
    if state.seating is not Seating.GROUP:
        return Vote.HOT_SEAT_PROMPT
    given, total = turnout(state)
    return Vote.PROGRESS.format(given=given, total=total)


def _verdict_caption(
    state: GameSessionState,
    player: PlayerState,
    counts: Mapping[int, int],
    winner: Winner | None,
) -> str:
    lines = [
        (Vote.VERDICT_SPY if player.is_spy else Vote.VERDICT_CIVILIAN).format(name=player.name)
    ]
    if state.seating is Seating.GROUP:
        lines.extend(
            Vote.TALLY_LINE.format(name=state.players[order_index].name, votes=votes)
            for order_index, votes in sorted(counts.items(), key=lambda pair: -pair[1])
        )
    if winner is not None:
        lines.append(win_line(winner, misfire=misfired(state)))
    return "\n".join(lines)


def _ballot_keyboard(state: GameSessionState) -> InlineKeyboardMarkup:
    ballot = state.ballot
    options = tuple(ballot.options) if isinstance(ballot, EliminationBallot) else ()
    rows = [
        [_pick_button(state, order_index) for order_index in pair]
        for pair in batched(options, 2, strict=False)
    ]
    rows.append(
        [button(Buttons.BACK_TO_TALK, VoteCB(action=VoteAction.BACK, session_id=state.session_id))]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _verdict_keyboard(state: GameSessionState, winner: Winner | None) -> InlineKeyboardMarkup:
    if winner is None:
        return single_button(
            Buttons.CONTINUE_TALK,
            VoteCB(action=VoteAction.CONTINUE, session_id=state.session_id),
        )
    return single_button(
        Buttons.SHOW_RESULT,
        FinalCB(action=FinalAction.RESULT, session_id=state.session_id),
    )


def _pick_button(state: GameSessionState, order_index: int) -> InlineKeyboardButton:
    return button(
        state.players[order_index].name,
        PickCB(session_id=state.session_id, order_index=order_index),
    )
