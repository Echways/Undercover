from aiogram import Bot
from aiogram.types import CallbackQuery, Chat
from aiogram_dialog import DialogManager
from aiogram_dialog.widgets.kbd import Button
from aiogram_dialog.widgets.kbd.button import OnClick

from undercover.bot.phases import PhaseStarter
from undercover.bot.routers.setup.draft import SetupDraft, restart, set_error
from undercover.game.catalog import CachedCatalog
from undercover.game.engine import EmptyWordCatalogError, create_session, secure_rng
from undercover.game.rules import GameRulesError
from undercover.log import get_logger
from undercover.redis.game_state import GameStateRepository
from undercover.texts import Setup as SetupTexts
from undercover.texts import empty_catalog_text

logger = get_logger(__name__)


def play(catalog: CachedCatalog, start_reveal: PhaseStarter) -> OnClick:
    async def on_play(
        callback: CallbackQuery, _button: Button, dialog_manager: DialogManager
    ) -> None:
        draft = SetupDraft.read(dialog_manager)
        if draft.players_count is None or len(draft.names) != draft.players_count:
            logger.warning("setup.draft_incomplete", draft=repr(draft))
            await restart(dialog_manager, SetupTexts.BROKEN_DRAFT)
            return

        games: GameStateRepository = dialog_manager.middleware_data["games"]
        chat: Chat = dialog_manager.middleware_data["event_chat"]
        bot: Bot = dialog_manager.middleware_data["bot"]
        settings = draft.settings
        settings.category_ids = draft.category_ids

        try:
            async with catalog.open() as words:
                state = await create_session(
                    chat_id=chat.id,
                    host_user_id=callback.from_user.id,
                    player_names=draft.names,
                    spies_count=settings.spies_count,
                    words=words,
                    rng=secure_rng(),
                    category_ids=settings.category_ids,
                    ruleset=settings.ruleset,
                    turn_seconds=settings.turn_seconds,
                )
        except EmptyWordCatalogError:
            logger.exception(
                "setup.empty_catalog", chat_id=chat.id, categories=sorted(settings.category_ids)
            )
            set_error(dialog_manager, empty_catalog_text(settings.category_ids))
            return
        except GameRulesError:
            logger.exception("setup.draft_refused", chat_id=chat.id, draft=repr(draft))
            await restart(dialog_manager, SetupTexts.BROKEN_DRAFT)
            return

        logger.info(
            "setup.session_created",
            chat_id=chat.id,
            session_id=state.session_id,
            players=len(state.players),
            spies=settings.spies_count,
            categories=sorted(settings.category_ids),
        )
        await dialog_manager.done()
        await start_reveal(bot, games, state)

    return on_play
