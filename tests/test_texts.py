import ast
import re
from pathlib import Path

import pytest

import undercover.bot
from undercover import texts
from undercover.media import card_renderer

BOT_PACKAGE = Path(undercover.bot.__file__).parent
CARD_RENDERER = Path(card_renderer.__file__)

RUSSIAN = re.compile(r"[А-Яа-яЁё]")

SCREENS = (
    texts.Start,
    texts.Setup,
    texts.Reveal,
    texts.Discussion,
    texts.Errors,
    texts.Cards,
)

USER_FACING_CALLS = frozenset(
    {
        "answer",
        "reply",
        "edit_text",
        "send_message",
        "show_or_advance_card",
        "Const",
        "Format",
        "Multi",
        "ValueError",
        "_set_error",
        "_restart",
    }
)


def modules_with_handlers() -> list[Path]:
    return sorted(path for path in BOT_PACKAGE.rglob("*.py") if path.name != "__init__.py")


def called_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return ""


def literals_shown_to_players(source: str) -> list[str]:
    found: list[str] = []
    for call in ast.walk(ast.parse(source)):
        if not isinstance(call, ast.Call) or called_name(call) not in USER_FACING_CALLS:
            continue
        arguments = [*call.args, *(keyword.value for keyword in call.keywords)]
        for argument in arguments:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                if argument.value.strip():
                    found.append(argument.value)
            elif isinstance(argument, ast.JoinedStr):
                found.append(ast.unparse(argument))
    return found


@pytest.mark.parametrize("module", modules_with_handlers(), ids=lambda path: path.name)
def test_handlers_show_no_literals_of_their_own(module: Path) -> None:
    found = literals_shown_to_players(module.read_text(encoding="utf-8"))

    assert found == [], f"{module.name}: текст на экране мимо texts.py — {found}"


def test_the_guard_notices_a_literal_that_slipped_in() -> None:
    slipped = "await callback.answer('Партия не найдена', show_alert=True)"

    assert literals_shown_to_players(slipped) == ["Партия не найдена"]


def test_the_guard_leaves_logs_alone() -> None:
    logging_call = 'logger.info("партия %s собрана", state.session_id)'

    assert literals_shown_to_players(logging_call) == []


def test_every_screen_speaks_russian() -> None:
    for screen in SCREENS:
        for name, value in vars(screen).items():
            if name.startswith("_"):
                continue
            assert isinstance(value, str) and value.strip(), f"{screen.__name__}.{name}"


def test_the_brand_is_written_in_latin() -> None:
    assert texts.BRAND == "Undercover"
    assert "Undercover" in texts.Start.GREETING
    assert "Undercover" in texts.Setup.ASK_PLAYERS_COUNT
    assert texts.Cards.SPY_PLATE == "UNDERCOVER"


def module_level_russian_constants(source: str) -> list[str]:
    found: list[str] = []
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign | ast.AnnAssign):
            continue
        value = node.value
        if (
            isinstance(value, ast.Constant)
            and isinstance(value.value, str)
            and RUSSIAN.search(value.value)
        ):
            found.append(value.value)
    return found


def test_the_card_renderer_keeps_no_texts_of_its_own() -> None:
    found = module_level_russian_constants(CARD_RENDERER.read_text(encoding="utf-8"))

    assert found == [], f"подпись карточки мимо texts.py — {found}"


def test_the_guard_notices_a_caption_that_slipped_back() -> None:
    slipped = 'HIDDEN_CAPTION: Final = "ПЕРЕДАЙТЕ ТЕЛЕФОН"'

    assert module_level_russian_constants(slipped) == ["ПЕРЕДАЙТЕ ТЕЛЕФОН"]
