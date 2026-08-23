import ast
import re
from datetime import timedelta
from pathlib import Path

import pytest

import undercover.bot
import undercover.media
from undercover import texts
from undercover.game.models import Ruleset, Winner
from undercover.game.voting import Refusal

BOT_PACKAGE = Path(undercover.bot.__file__).parent
MEDIA_PACKAGE = Path(undercover.media.__file__).parent

RUSSIAN = re.compile(r"[А-Яа-яЁё]")

ARROWS = "\u2190-\u21ff"
GEOMETRIC_SHAPES = "\u25a0-\u25ff"
DINGBATS = "\u2600-\u27bf"
MISCELLANEOUS_SYMBOLS = "\u2b00-\u2bff"
VARIATION_SELECTOR = "\ufe0f"
EMOJI = "\U0001f000-\U0001faff"

PICTOGRAPH = re.compile(
    f"[{ARROWS}{GEOMETRIC_SHAPES}{DINGBATS}{MISCELLANEOUS_SYMBOLS}{VARIATION_SELECTOR}{EMOJI}]"
)

SCREENS = (
    texts.Start,
    texts.Setup,
    texts.Rules,
    texts.Lobby,
    texts.Reveal,
    texts.Discussion,
    texts.Vote,
    texts.Timer,
    texts.Stats,
    texts.Errors,
    texts.Cards,
)

TEXT_CLASSES = (*SCREENS, texts.Buttons)

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


def shown_strings(source: type) -> list[tuple[str, str]]:
    return [
        (f"{source.__name__}.{name}", value)
        for name, value in vars(source).items()
        if not name.startswith("_") and isinstance(value, str)
    ]


def test_every_screen_speaks_russian() -> None:
    for screen in SCREENS:
        for name, value in vars(screen).items():
            if name.startswith("_"):
                continue
            assert isinstance(value, str) and value.strip(), f"{screen.__name__}.{name}"


@pytest.mark.parametrize("source", TEXT_CLASSES, ids=lambda source: source.__name__)
def test_no_screen_wears_an_emoji(source: type) -> None:
    dressed = [name for name, value in shown_strings(source) if PICTOGRAPH.search(value)]

    assert dressed == [], f"пиктограмма в тексте — {dressed}"


def test_the_guard_notices_an_emoji_that_slipped_back() -> None:
    assert PICTOGRAPH.search("\u25b6\ufe0f Играть")
    assert PICTOGRAPH.search("\U0001f575\ufe0f Показать шпиона")
    assert not PICTOGRAPH.search("«Пётр» уже в составе — добавьте прозвище…")


def test_the_hall_of_fame_speaks_of_the_brand() -> None:
    assert texts.BRAND in texts.Stats.TITLE


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (1, "раз"),
        (2, "раза"),
        (4, "раза"),
        (5, "раз"),
        (11, "раз"),
        (12, "раз"),
        (14, "раз"),
        (21, "раз"),
        (22, "раза"),
        (112, "раз"),
        (121, "раз"),
    ],
)
def test_the_count_of_falls_agrees_with_the_number(count: int, expected: str) -> None:
    assert texts.plural(count, texts.TIMES) == expected


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


@pytest.mark.parametrize("module", sorted(MEDIA_PACKAGE.glob("*.py")), ids=lambda path: path.name)
def test_the_media_package_keeps_no_texts_of_its_own(module: Path) -> None:
    found = module_level_russian_constants(module.read_text(encoding="utf-8"))

    assert found == [], f"подпись карточки мимо texts.py — {found}"


def test_the_guard_notices_a_caption_that_slipped_back() -> None:
    slipped = 'HIDDEN_CAPTION: Final = "ПЕРЕДАЙТЕ ТЕЛЕФОН"'

    assert module_level_russian_constants(slipped) == ["ПЕРЕДАЙТЕ ТЕЛЕФОН"]


def test_every_refusal_has_something_to_say() -> None:
    for refusal in Refusal:
        assert texts.VOTE_REFUSALS[refusal].strip()


def test_every_winner_has_a_caption_and_a_line() -> None:
    for winner in Winner:
        assert texts.WIN_CAPTIONS[winner].strip()
        assert texts.WIN_LINES[winner].strip()


def test_every_ruleset_has_a_button_name_and_a_line_in_the_lobby() -> None:
    for ruleset in Ruleset:
        assert texts.RULESET_NAMES[ruleset].strip()
        assert texts.RULESET_LINES[ruleset].strip()


def test_the_rules_describe_every_ruleset_the_lobby_offers() -> None:
    spelled_out = texts.Rules.FULL.casefold()

    assert [name for name in texts.RULESET_NAMES.values() if name not in spelled_out] == []


def test_the_misfire_line_belongs_to_the_spies() -> None:
    assert texts.win_line(Winner.SPIES, misfire=True) == texts.Vote.SPIES_WIN_MISFIRE
    assert texts.win_line(Winner.SPIES) == texts.Vote.SPIES_WIN
    assert texts.win_line(Winner.CIVILIANS, misfire=True) == texts.Vote.CIVILIANS_WIN


def test_the_duration_reads_in_minutes() -> None:
    assert texts.duration_text(timedelta(seconds=0)) == "меньше минуты"
    assert texts.duration_text(timedelta(seconds=59)) == "меньше минуты"
    assert texts.duration_text(timedelta(seconds=60)) == "1 мин"
    assert texts.duration_text(timedelta(minutes=59)) == "59 мин"


def test_a_long_game_reads_in_hours() -> None:
    assert texts.duration_text(timedelta(minutes=60)) == "1 ч 00 мин"
    assert texts.duration_text(timedelta(minutes=125)) == "2 ч 05 мин"
