import inspect
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from PIL import Image, ImageChops

from undercover.game.models import Ruleset, Winner
from undercover.game.summary import GameSummary, Suspect
from undercover.media.blocks import Block, headline
from undercover.media.canvas import render
from undercover.media.card_renderer import (
    render_ballot_card,
    render_civilian_card,
    render_hidden_card,
    render_result_card,
    render_speaker_card,
    render_spy_card,
    render_verdict_card,
)
from undercover.media.layout import (
    BACKGROUND_NEUTRAL,
    BACKGROUND_UNDERCOVER,
    CARD_FORMAT,
    CARD_SIZE,
    CONTENT_HEIGHT,
    CONTENT_WIDTH,
    FONT_BOLD,
    FONT_REGULAR,
    GLOW_COLD,
    HEADLINE_MAX_SIZE,
    HINT_MAX_SIZE,
    SAFE_MARGIN,
    TEMPLATES_DIR,
)
from undercover.media.summary_card import render_summary_card
from undercover.media.typography import font, plain, shorten, text_width, wrap

RENDERERS: tuple[Callable[..., bytes], ...] = (
    render_hidden_card,
    render_civilian_card,
    render_spy_card,
    render_speaker_card,
    render_result_card,
    render_ballot_card,
    render_verdict_card,
)


def open_card(payload: bytes) -> Image.Image:
    image = Image.open(BytesIO(payload))
    image.load()
    return image


def test_hidden_card_is_a_photo_of_card_size() -> None:
    with open_card(render_hidden_card("Аня")) as card:
        assert card.format == CARD_FORMAT
        assert card.size == CARD_SIZE


def test_civilian_card_is_a_photo_of_card_size() -> None:
    with open_card(render_civilian_card("Аня", "пицца")) as card:
        assert card.format == CARD_FORMAT
        assert card.size == CARD_SIZE


def test_spy_card_is_a_photo_of_card_size() -> None:
    with open_card(render_spy_card("Аня", "её режут на куски")) as card:
        assert card.format == CARD_FORMAT
        assert card.size == CARD_SIZE


def test_speaker_card_is_a_photo_of_card_size() -> None:
    with open_card(render_speaker_card("Аня")) as card:
        assert card.format == CARD_FORMAT
        assert card.size == CARD_SIZE


def test_result_card_is_a_photo_of_card_size() -> None:
    with open_card(render_result_card(("Аня",), "пицца")) as card:
        assert card.format == CARD_FORMAT
        assert card.size == CARD_SIZE


def test_ballot_card_is_a_photo_of_card_size() -> None:
    with open_card(render_ballot_card()) as card:
        assert card.format == CARD_FORMAT
        assert card.size == CARD_SIZE


def test_verdict_card_is_a_photo_of_card_size() -> None:
    with open_card(render_verdict_card("Аня", is_spy=True)) as card:
        assert card.format == CARD_FORMAT
        assert card.size == CARD_SIZE


def test_renderers_are_synchronous() -> None:
    for renderer in RENDERERS:
        assert not inspect.iscoroutinefunction(renderer), renderer.__name__


JPEG_ARTEFACT_TOLERANCE = 24


def background_corner(file_name: str) -> tuple[int, ...]:
    with Image.open(TEMPLATES_DIR / file_name) as background:
        corner = background.convert("RGB").getpixel((10, 10))
    assert isinstance(corner, tuple)
    return corner


def card_corner(payload: bytes) -> tuple[int, ...]:
    with open_card(payload) as card:
        corner = card.convert("RGB").getpixel((10, 10))
    assert isinstance(corner, tuple)
    return corner


def assert_same_corner(payload: bytes, background_name: str) -> None:
    corner = card_corner(payload)
    expected = background_corner(background_name)
    assert all(
        abs(actual - wanted) <= JPEG_ARTEFACT_TOLERANCE
        for actual, wanted in zip(corner, expected, strict=True)
    ), f"{corner} != {expected}"


def test_spy_card_is_drawn_on_the_undercover_background() -> None:
    assert_same_corner(render_spy_card("Аня", "её режут на куски"), BACKGROUND_UNDERCOVER)


def test_civilian_and_hidden_cards_are_drawn_on_the_neutral_background() -> None:
    assert_same_corner(render_civilian_card("Аня", "пицца"), BACKGROUND_NEUTRAL)
    assert_same_corner(render_hidden_card("Аня"), BACKGROUND_NEUTRAL)


def test_speaker_card_is_drawn_on_the_neutral_background() -> None:
    assert_same_corner(render_speaker_card("Аня"), BACKGROUND_NEUTRAL)


def test_result_card_is_drawn_on_the_undercover_background() -> None:
    assert_same_corner(render_result_card(("Аня",), "пицца"), BACKGROUND_UNDERCOVER)


def test_spy_and_civilian_cards_of_one_player_differ() -> None:
    assert render_spy_card("Аня", "пицца") != render_civilian_card("Аня", "пицца")


def test_cards_of_different_players_differ() -> None:
    assert render_hidden_card("Аня") != render_hidden_card("Боря")


def test_speaker_cards_of_different_players_differ() -> None:
    assert render_speaker_card("Аня") != render_speaker_card("Боря")


def test_result_card_names_every_spy() -> None:
    assert render_result_card(("Аня", "Боря"), "пицца") != render_result_card(("Аня",), "пицца")


def test_result_card_shows_the_word_that_was_played() -> None:
    assert render_result_card(("Аня",), "пицца") != render_result_card(("Аня",), "пельмени")


def test_same_input_renders_the_same_bytes() -> None:
    assert render_civilian_card("Аня", "пицца") == render_civilian_card("Аня", "пицца")


def test_whitespace_around_input_does_not_change_the_card() -> None:
    assert render_civilian_card("  Аня ", "пицца\n\tгодная") == render_civilian_card(
        "Аня", "пицца годная"
    )


@pytest.mark.parametrize(
    ("render", "args"),
    [
        (render_hidden_card, ("   ",)),
        (render_civilian_card, ("", "пицца")),
        (render_civilian_card, ("Аня", "\n")),
        (render_spy_card, (" \t ", "её режут на куски")),
        (render_spy_card, ("Аня", "")),
        (render_speaker_card, ("   ",)),
        (render_result_card, ((), "пицца")),
        (render_result_card, (("Аня",), " ")),
        (render_result_card, ((" ",), "пицца")),
    ],
)
def test_blank_input_is_rejected(render: Callable[..., bytes], args: tuple[object, ...]) -> None:
    with pytest.raises(ValueError):
        render(*args)


LONG_NAME = "Аполлинария" * 40
LONG_TEXT = "невыносимо длинная подсказка про то самое слово " * 20

LAYOUT_CASES: tuple[tuple[Callable[..., bytes], tuple[object, ...], str], ...] = (
    (render_hidden_card, ("Аня",), BACKGROUND_NEUTRAL),
    (render_civilian_card, ("Аня", "пицца"), BACKGROUND_NEUTRAL),
    (render_spy_card, ("Аня", "её режут на куски"), BACKGROUND_UNDERCOVER),
    (render_hidden_card, (LONG_NAME,), BACKGROUND_NEUTRAL),
    (render_civilian_card, (LONG_NAME, LONG_TEXT), BACKGROUND_NEUTRAL),
    (render_spy_card, (LONG_NAME, LONG_TEXT), BACKGROUND_UNDERCOVER),
    (render_speaker_card, ("Аня",), BACKGROUND_NEUTRAL),
    (render_speaker_card, (LONG_NAME,), BACKGROUND_NEUTRAL),
    (render_result_card, (("Аня",), "пицца"), BACKGROUND_UNDERCOVER),
    (
        render_result_card,
        (tuple(f"{LONG_NAME}{index}" for index in range(5)), LONG_TEXT),
        BACKGROUND_UNDERCOVER,
    ),
    (render_ballot_card, (), BACKGROUND_NEUTRAL),
    (render_verdict_card, ("Аня", True), BACKGROUND_UNDERCOVER),
    (render_verdict_card, (LONG_NAME, False), BACKGROUND_NEUTRAL),
    (
        render_result_card,
        (tuple(f"{LONG_NAME}{index}" for index in range(5)), LONG_TEXT, Winner.SPIES),
        BACKGROUND_UNDERCOVER,
    ),
)


def content_box(payload: bytes, background_name: str) -> tuple[int, int, int, int]:
    """Рамка нарисованного: всё, что отличается от подложки сильнее артефактов кодека."""
    with (
        open_card(payload) as card,
        Image.open(TEMPLATES_DIR / background_name) as background,
    ):
        difference = ImageChops.difference(card.convert("RGB"), background.convert("RGB"))
        box = difference.convert("L").point(lambda level: level > JPEG_ARTEFACT_TOLERANCE).getbbox()
    assert box is not None, "на карточке ничего не нарисовано"
    return box


@pytest.mark.parametrize(("render", "args", "background"), LAYOUT_CASES)
def test_content_stays_inside_the_safe_margin(
    render: Callable[..., bytes], args: tuple[object, ...], background: str
) -> None:
    left, top, right, bottom = content_box(render(*args), background)
    width, height = CARD_SIZE

    assert left >= SAFE_MARGIN
    assert top >= SAFE_MARGIN
    assert right <= width - SAFE_MARGIN
    assert bottom <= height - SAFE_MARGIN


def test_wrap_breaks_a_long_word_after_a_hyphen() -> None:
    face = font(FONT_BOLD, HEADLINE_MAX_SIZE)

    assert wrap("Мария-Антуанетта", face, CONTENT_WIDTH, 0) == ["Мария-", "Антуанетта"]


def test_wrap_falls_back_to_letters_when_there_is_nowhere_to_break() -> None:
    word = "Аполлинария" * 3
    face = font(FONT_BOLD, HEADLINE_MAX_SIZE)

    lines = wrap(word, face, CONTENT_WIDTH, 0)

    assert "".join(lines) == word
    assert all(text_width(face, line, 0) <= CONTENT_WIDTH for line in lines)


def test_wrap_keeps_words_whole_while_they_fit() -> None:
    face = font(FONT_REGULAR, HINT_MAX_SIZE)

    assert wrap("его режут на куски", face, CONTENT_WIDTH, 0) == ["его режут на куски"]


def test_shorten_keeps_a_line_that_already_fits() -> None:
    face = font(FONT_REGULAR, HINT_MAX_SIZE)

    assert shorten("Аня", face, CONTENT_WIDTH, 0) == "Аня"


def test_shorten_cuts_a_long_line_down_to_the_width() -> None:
    face = font(FONT_BOLD, HEADLINE_MAX_SIZE)

    result = shorten("Аполлинария" * 5, face, CONTENT_WIDTH, 0)

    assert result.endswith("…")
    assert text_width(face, result, 0) <= CONTENT_WIDTH


def test_shorten_counts_tracking_in_the_width() -> None:
    face = font(FONT_BOLD, HEADLINE_MAX_SIZE)

    tracked = shorten("Аполлинария" * 5, face, CONTENT_WIDTH, 12)

    assert text_width(face, tracked, 12) <= CONTENT_WIDTH


def test_plain_squeezes_the_whitespace_out() -> None:
    assert plain("  Аня \n\tПетровна ", "имя игрока") == "Аня Петровна"


def test_plain_rejects_a_blank_value_and_names_the_field() -> None:
    with pytest.raises(ValueError, match="имя игрока"):
        plain("  \n ", "имя игрока")


WORDMARK_BAND = (SAFE_MARGIN, CARD_SIZE[1] - 200, CARD_SIZE[0] - SAFE_MARGIN, CARD_SIZE[1] - 60)

WORDMARK_CASES: tuple[tuple[Callable[..., bytes], tuple[object, ...], str], ...] = (
    (render_hidden_card, ("Аня",), BACKGROUND_NEUTRAL),
    (render_civilian_card, ("Аня", "пицца"), BACKGROUND_NEUTRAL),
    (render_speaker_card, ("Аня",), BACKGROUND_NEUTRAL),
    (render_spy_card, ("Аня", "её режут на куски"), BACKGROUND_UNDERCOVER),
    (render_result_card, (("Аня",), "пицца"), BACKGROUND_UNDERCOVER),
    (render_ballot_card, (), BACKGROUND_NEUTRAL),
    (render_verdict_card, ("Аня", False), BACKGROUND_NEUTRAL),
)


@pytest.mark.parametrize(("render", "args", "background"), WORDMARK_CASES)
def test_every_card_is_signed_at_the_bottom(
    render: Callable[..., bytes], args: tuple[object, ...], background: str
) -> None:
    with (
        open_card(render(*args)) as card,
        Image.open(TEMPLATES_DIR / background) as plate,
    ):
        band = ImageChops.difference(
            card.convert("RGB").crop(WORDMARK_BAND),
            plate.convert("RGB").crop(WORDMARK_BAND),
        )

    assert (
        band.convert("L").point(lambda level: level > JPEG_ARTEFACT_TOLERANCE).getbbox() is not None
    )


PROMO = "t.me/undercover_bot"


def signed_blocks() -> tuple[Block, ...]:
    return (headline("Аня"),)


def test_the_promo_line_changes_the_footer() -> None:
    quiet = render(BACKGROUND_NEUTRAL, GLOW_COLD, signed_blocks())
    promoted = render(BACKGROUND_NEUTRAL, GLOW_COLD, signed_blocks(), PROMO)

    assert quiet != promoted


def test_the_promo_line_stays_inside_the_safe_margin() -> None:
    _, _, _, bottom = content_box(
        render(BACKGROUND_NEUTRAL, GLOW_COLD, signed_blocks(), PROMO), BACKGROUND_NEUTRAL
    )

    assert bottom <= CARD_SIZE[1] - SAFE_MARGIN


def test_the_content_height_leaves_room_for_the_footer() -> None:
    assert CARD_SIZE[1] - 2 * SAFE_MARGIN > CONTENT_HEIGHT
    assert CONTENT_HEIGHT > 0


def test_the_ballot_card_is_drawn_on_the_neutral_background() -> None:
    assert_same_corner(render_ballot_card(), BACKGROUND_NEUTRAL)


def test_the_verdict_takes_its_colour_from_the_role() -> None:
    assert_same_corner(render_verdict_card("Аня", is_spy=True), BACKGROUND_UNDERCOVER)
    assert_same_corner(render_verdict_card("Аня", is_spy=False), BACKGROUND_NEUTRAL)


def test_the_same_name_looks_different_for_a_spy_and_for_a_civilian() -> None:
    assert render_verdict_card("Аня", is_spy=True) != render_verdict_card("Аня", is_spy=False)


def test_a_nameless_verdict_is_rejected() -> None:
    with pytest.raises(ValueError):
        render_verdict_card("   ", is_spy=False)


def test_the_result_card_says_who_won_when_there_is_a_winner() -> None:
    quiet = render_result_card(("Аня",), "пицца")
    civilians = render_result_card(("Аня",), "пицца", winner=Winner.CIVILIANS)
    spies = render_result_card(("Аня",), "пицца", winner=Winner.SPIES)

    assert quiet != civilians
    assert civilians != spies
    assert quiet != spies


SUMMARY_STARTED_AT = datetime(2026, 8, 23, 20, 0, tzinfo=UTC)

TABLE: tuple[Suspect, ...] = (
    Suspect(name="Аня", is_spy=False, out_order=None),
    Suspect(name="Борис", is_spy=True, out_order=2),
    Suspect(name="Вера", is_spy=False, out_order=1),
)


def summary(
    *,
    case_number: int | None = 17,
    winner: Winner | None = Winner.CIVILIANS,
    ruleset: Ruleset = Ruleset.CLASSIC,
    suspects: tuple[Suspect, ...] = TABLE,
    word: str = "пицца",
    hints: tuple[str, ...] = ("её режут на куски",),
    rounds: int = 3,
    duration: timedelta = timedelta(minutes=6),
) -> GameSummary:
    return GameSummary(
        case_number=case_number,
        opened_at=SUMMARY_STARTED_AT,
        winner=winner,
        ruleset=ruleset,
        suspects=suspects,
        word=word,
        hints=hints,
        rounds=rounds,
        duration=duration,
    )


def test_the_summary_card_is_a_photo_of_card_size() -> None:
    with open_card(render_summary_card(summary())) as card:
        assert card.format == CARD_FORMAT
        assert card.size == CARD_SIZE


def test_the_civilians_take_the_cold_card() -> None:
    assert_same_corner(render_summary_card(summary()), BACKGROUND_NEUTRAL)


def test_the_spies_take_the_warm_card() -> None:
    assert_same_corner(render_summary_card(summary(winner=Winner.SPIES)), BACKGROUND_UNDERCOVER)


def test_an_early_reveal_stays_warm() -> None:
    assert_same_corner(render_summary_card(summary(winner=None)), BACKGROUND_UNDERCOVER)


def test_the_summary_card_names_every_player() -> None:
    shorter = summary(suspects=TABLE[:2])

    assert render_summary_card(summary()) != render_summary_card(shorter)


def test_the_summary_card_shows_the_word_that_was_played() -> None:
    assert render_summary_card(summary()) != render_summary_card(summary(word="пельмени"))


def test_the_case_number_falls_back_to_the_date() -> None:
    assert render_summary_card(summary()) != render_summary_card(summary(case_number=None))


def test_the_promo_line_only_appears_when_it_is_given() -> None:
    assert render_summary_card(summary()) != render_summary_card(summary(), "t.me/undercover_bot")


def test_the_same_summary_renders_the_same_bytes() -> None:
    assert render_summary_card(summary()) == render_summary_card(summary())


def test_an_empty_roster_is_rejected() -> None:
    with pytest.raises(ValueError):
        render_summary_card(summary(suspects=()))


def test_a_nameless_player_is_rejected() -> None:
    with pytest.raises(ValueError):
        render_summary_card(summary(suspects=(Suspect(name="  ", is_spy=True, out_order=None),)))


def test_a_blank_word_is_rejected() -> None:
    with pytest.raises(ValueError):
        render_summary_card(summary(word="\n"))


def test_stray_whitespace_does_not_change_the_card() -> None:
    assert render_summary_card(summary(word="  пицца ")) == render_summary_card(summary())


CROWD = tuple(
    Suspect(name=f"Аполлинария-Иннокентия {index}", is_spy=index < 5, out_order=index or None)
    for index in range(16)
)

SUMMARY_LAYOUT_CASES: tuple[tuple[GameSummary, str], ...] = (
    (summary(), BACKGROUND_NEUTRAL),
    (summary(winner=Winner.SPIES), BACKGROUND_UNDERCOVER),
    (summary(winner=None), BACKGROUND_UNDERCOVER),
    (summary(suspects=TABLE[:2]), BACKGROUND_NEUTRAL),
    (
        summary(
            suspects=CROWD,
            word="невыносимо длинное загаданное словосочетание про ёлку",
            hints=tuple(f"подсказка номер {index} про то самое слово" for index in range(5)),
            ruleset=Ruleset.SUDDEN_DEATH,
            duration=timedelta(hours=2, minutes=5),
            rounds=11,
        ),
        BACKGROUND_NEUTRAL,
    ),
)


@pytest.mark.parametrize(("case", "background"), SUMMARY_LAYOUT_CASES)
def test_the_summary_stays_inside_the_safe_margin(case: GameSummary, background: str) -> None:
    left, top, right, bottom = content_box(
        render_summary_card(case, "t.me/undercover_bot"), background
    )
    width, height = CARD_SIZE

    assert left >= SAFE_MARGIN
    assert top >= SAFE_MARGIN
    assert right <= width - SAFE_MARGIN
    assert bottom <= height - SAFE_MARGIN
