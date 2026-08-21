import inspect
from collections.abc import Callable
from io import BytesIO

import pytest
from PIL import Image, ImageChops

from undercover.media.card_renderer import (
    BACKGROUND_NEUTRAL,
    BACKGROUND_UNDERCOVER,
    CARD_FORMAT,
    CARD_SIZE,
    CONTENT_WIDTH,
    FONT_BOLD,
    FONT_REGULAR,
    HEADLINE_MAX_SIZE,
    HINT_MAX_SIZE,
    SAFE_MARGIN,
    TEMPLATES_DIR,
    _font,
    _text_width,
    _wrap,
    render_civilian_card,
    render_hidden_card,
    render_result_card,
    render_speaker_card,
    render_spy_card,
)

RENDERERS: tuple[Callable[..., bytes], ...] = (
    render_hidden_card,
    render_civilian_card,
    render_spy_card,
    render_speaker_card,
    render_result_card,
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


def test_renderers_are_synchronous() -> None:
    for render in RENDERERS:
        assert not inspect.iscoroutinefunction(render), render.__name__


# Карточка сохраняется в JPEG, поэтому пиксели фона совпадают лишь с точностью до артефактов.
CODEC_TOLERANCE = 24


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
        abs(actual - wanted) <= CODEC_TOLERANCE
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
)


def content_box(payload: bytes, background_name: str) -> tuple[int, int, int, int]:
    """Рамка нарисованного: всё, что отличается от подложки сильнее артефактов кодека."""
    with (
        open_card(payload) as card,
        Image.open(TEMPLATES_DIR / background_name) as background,
    ):
        difference = ImageChops.difference(card.convert("RGB"), background.convert("RGB"))
        box = difference.convert("L").point(lambda level: level > CODEC_TOLERANCE).getbbox()
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
    font = _font(FONT_BOLD, HEADLINE_MAX_SIZE)

    assert _wrap("Мария-Антуанетта", font, CONTENT_WIDTH, 0) == ["Мария-", "Антуанетта"]


def test_wrap_falls_back_to_letters_when_there_is_nowhere_to_break() -> None:
    word = "Аполлинария" * 3
    font = _font(FONT_BOLD, HEADLINE_MAX_SIZE)

    lines = _wrap(word, font, CONTENT_WIDTH, 0)

    assert "".join(lines) == word
    assert all(_text_width(font, line, 0) <= CONTENT_WIDTH for line in lines)


def test_wrap_keeps_words_whole_while_they_fit() -> None:
    font = _font(FONT_REGULAR, HINT_MAX_SIZE)

    assert _wrap("его режут на куски", font, CONTENT_WIDTH, 0) == ["его режут на куски"]


WORDMARK_BAND = (SAFE_MARGIN, CARD_SIZE[1] - 200, CARD_SIZE[0] - SAFE_MARGIN, CARD_SIZE[1] - 60)

WORDMARK_CASES: tuple[tuple[Callable[..., bytes], tuple[object, ...], str], ...] = (
    (render_hidden_card, ("Аня",), BACKGROUND_NEUTRAL),
    (render_civilian_card, ("Аня", "пицца"), BACKGROUND_NEUTRAL),
    (render_speaker_card, ("Аня",), BACKGROUND_NEUTRAL),
    (render_spy_card, ("Аня", "её режут на куски"), BACKGROUND_UNDERCOVER),
    (render_result_card, (("Аня",), "пицца"), BACKGROUND_UNDERCOVER),
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

    assert band.convert("L").point(lambda level: level > CODEC_TOLERANCE).getbbox() is not None
