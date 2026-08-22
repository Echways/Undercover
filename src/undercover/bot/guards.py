from aiogram.types import CallbackQuery

from undercover.game.models import GameMode, GameSessionState, GameStatus
from undercover.redis.game_state import GameStateRepository
from undercover.texts import Discussion, Errors


def may_act(state: GameSessionState, user_id: int) -> bool:
    if user_id == state.host_user_id:
        return True
    return state.mode is GameMode.GROUP and _current_speaker_id(state) == user_id


async def load_game_in_phase(
    callback: CallbackQuery,
    session_id: str,
    games: GameStateRepository,
    expected: GameStatus,
    wrong_phase: str,
) -> GameSessionState | None:
    state = await games.load(session_id)
    if state is None:
        await callback.answer(Errors.SESSION_NOT_FOUND, show_alert=True)
        return None
    if state.status is not expected:
        await callback.answer(wrong_phase, show_alert=True)
        return None
    if not may_act(state, callback.from_user.id):
        await callback.answer(Errors.NOT_HOST, show_alert=True)
        return None
    return state


async def load_discussion(
    callback: CallbackQuery, session_id: str, games: GameStateRepository
) -> GameSessionState | None:
    return await load_game_in_phase(
        callback, session_id, games, GameStatus.DISCUSSION, Discussion.WRONG_PHASE
    )


async def load_finished(
    callback: CallbackQuery, session_id: str, games: GameStateRepository
) -> GameSessionState | None:
    return await load_game_in_phase(
        callback, session_id, games, GameStatus.FINISHED, Discussion.GAME_IS_ON
    )


def _current_speaker_id(state: GameSessionState) -> int | None:
    if state.status is not GameStatus.DISCUSSION:
        return None
    if not 0 <= state.discussion_cursor < len(state.discussion_order):
        return None
    order_index = state.discussion_order[state.discussion_cursor]
    if not 0 <= order_index < len(state.players):
        return None
    return state.players[order_index].user_id
