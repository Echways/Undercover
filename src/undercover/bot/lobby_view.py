from collections.abc import Sequence
from enum import StrEnum
from typing import Final

from aiogram import Bot
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.deep_linking import create_start_link

from undercover.bot.keyboards import button
from undercover.bot.message_utils import show_or_resend_text
from undercover.game.engine import MAX_PLAYERS, CategoryRecord
from undercover.game.models import LobbyState, LobbyView
from undercover.redis.lobby_state import LobbyRepository
from undercover.texts import Buttons, Lobby
from undercover.texts import Setup as SetupTexts

JOIN_PAYLOAD_PREFIX: Final = "join_"

MIN_CATEGORIES_TO_CHOOSE: Final = 2
CATEGORIES_PER_ROW: Final = 2


class LobbyAction(StrEnum):
    JOIN = "join"
    LEAVE = "leave"
    SPIES = "spies"
    TURN = "turn"
    CATEGORIES = "cats"
    CATEGORY = "cat"
    DONE = "done"
    PLAY = "play"


class LobbyCB(CallbackData, prefix="lobby"):
    action: LobbyAction
    value: int = 0


async def render_lobby(
    bot: Bot,
    lobbies: LobbyRepository,
    lobby: LobbyState,
    categories: Sequence[CategoryRecord],
) -> None:
    lobby.message_id = await show_or_resend_text(
        bot,
        lobby.chat_id,
        lobby.message_id,
        lobby_text(lobby, categories),
        lobby_keyboard(lobby, categories),
    )
    await lobbies.save(lobby)


async def join_link(bot: Bot, chat_id: int) -> str:
    return await create_start_link(bot, f"{JOIN_PAYLOAD_PREFIX}{chat_id}", encode=False)


def lobby_text(lobby: LobbyState, categories: Sequence[CategoryRecord]) -> str:
    if lobby.view is LobbyView.CATEGORIES:
        return Lobby.PICK_CATEGORIES

    return "\n\n".join(
        (
            Lobby.TITLE,
            _roster(lobby),
            Lobby.SUMMARY.format(
                players_count=len(lobby.players),
                spies_count=lobby.spies_count,
                chosen_categories=_chosen_categories(lobby, categories),
            ),
            Lobby.CALL,
        )
    )


def lobby_keyboard(lobby: LobbyState, categories: Sequence[CategoryRecord]) -> InlineKeyboardMarkup:
    if lobby.view is LobbyView.CATEGORIES:
        return _categories_keyboard(lobby, categories)
    return _roster_keyboard(lobby, categories)


def _roster(lobby: LobbyState) -> str:
    if not lobby.players:
        return Lobby.EMPTY_ROSTER
    return Lobby.ROSTER.format(
        count=len(lobby.players),
        limit=MAX_PLAYERS,
        names_list="\n".join(
            f"{number}. {player.name}" for number, player in enumerate(lobby.players, start=1)
        ),
    )


def _chosen_categories(lobby: LobbyState, categories: Sequence[CategoryRecord]) -> str:
    chosen = [item.title for item in categories if item.id in lobby.category_ids]
    return ", ".join(chosen) if chosen else SetupTexts.ALL_CATEGORIES


def _roster_keyboard(
    lobby: LobbyState, categories: Sequence[CategoryRecord]
) -> InlineKeyboardMarkup:
    settings = [
        _lobby_button(Buttons.SPIES_COUNT.format(count=lobby.spies_count), LobbyAction.SPIES),
        _lobby_button(_turn_label(lobby.turn_seconds), LobbyAction.TURN),
    ]
    if len(categories) >= MIN_CATEGORIES_TO_CHOOSE:
        settings.append(_lobby_button(Buttons.CHANGE_CATEGORIES, LobbyAction.CATEGORIES))

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _lobby_button(Buttons.JOIN_LOBBY, LobbyAction.JOIN),
                _lobby_button(Buttons.LEAVE_LOBBY, LobbyAction.LEAVE),
            ],
            settings,
            [_lobby_button(Buttons.PLAY, LobbyAction.PLAY)],
        ]
    )


def _categories_keyboard(
    lobby: LobbyState, categories: Sequence[CategoryRecord]
) -> InlineKeyboardMarkup:
    marks = [
        _lobby_button(
            (
                Lobby.CATEGORY_CHOSEN if item.id in lobby.category_ids else Lobby.CATEGORY_FREE
            ).format(title=item.title),
            LobbyAction.CATEGORY,
            item.id,
        )
        for item in categories
    ]
    rows = [
        marks[index : index + CATEGORIES_PER_ROW]
        for index in range(0, len(marks), CATEGORIES_PER_ROW)
    ]
    rows.append([_lobby_button(Buttons.CATEGORIES_DONE, LobbyAction.DONE)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _turn_label(seconds: int) -> str:
    return Buttons.TURN_OFF if seconds <= 0 else Buttons.TURN_LIMIT.format(seconds=seconds)


def _lobby_button(text: str, action: LobbyAction, value: int = 0) -> InlineKeyboardButton:
    return button(text, LobbyCB(action=action, value=value))
