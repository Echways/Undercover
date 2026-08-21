from aiogram.types import CallbackQuery

from undercover.game.models import GameSessionState, GameStatus
from undercover.redis.game_state import GameStateRepository
from undercover.texts import Errors


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
    if callback.from_user.id != state.host_user_id:
        await callback.answer(Errors.NOT_HOST, show_alert=True)
        return None
    return state
