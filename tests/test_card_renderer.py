import inspect
from collections.abc import Callable
from io import BytesIO

import pytest
from PIL import Image, ImageChops

from undercover.media.card_renderer import (
    BACKGROUND_NEUTRAL,
    BACKGROUND_UNDERCOVER,
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


def test_hidden_card_is_a_png_of_card_size() -> None:
    with open_card(render_hidden_card("Аня")) as card:
        assert card.format == "PNG"
        assert card.size == CARD_SIZE


def test_civilian_card_is_a_png_of_card_size() -> None:
    with open_card(render_civilian_card("Аня", "пицца")) as card:
        assert card.format == "PNG"
        assert card.size == CARD_SIZE


def test_spy_card_is_a_png_of_card_size() -> None:
    with open_card(render_spy_card("Аня", "её режут на куски")) as card:
        assert card.format == "PNG"
        assert card.size == CARD_SIZE


def test_speaker_card_is_a_png_of_card_size() -> None:
    with open_card(render_speaker_card("Аня")) as card:
        assert card.format == "PNG"
        assert card.size == CARD_SIZE


def test_result_card_is_a_png_of_card_size() -> None:
    with open_card(render_result_card(("Аня",), "пицца")) as card:
        assert card.format == "PNG"
        assert card.size == CARD_SIZE


def test_renderers_are_synchronous() -> None:
    for render in RENDERERS:
        assert not inspect.iscoroutinefunction(render), render.__name__


def background_corner(file_name: str) -> tuple[int, ...]:
    with Image.open(TEMPLATES_DIR / file_name) as background:
        return background.convert("RGB").getpixel((10, 10))


def test_spy_card_is_drawn_on_the_undercover_background() -> None:
    with open_card(render_spy_card("Аня", "её режут на куски")) as card:
        assert card.getpixel((10, 10)) == background_corner(BACKGROUND_UNDERCOVER)


def test_civilian_and_hidden_cards_are_drawn_on_the_neutral_background() -> None:
    neutral = background_corner(BACKGROUND_NEUTRAL)

    with open_card(render_civilian_card("Аня", "пицца")) as civilian:
        assert civilian.getpixel((10, 10)) == neutral
    with open_card(render_hidden_card("Аня")) as hidden:
        assert hidden.getpixel((10, 10)) == neutral


def test_speaker_card_is_drawn_on_the_neutral_background() -> None:
    with open_card(render_speaker_card("Аня")) as card:
        assert card.getpixel((10, 10)) == background_corner(BACKGROUND_NEUTRAL)


def test_result_card_is_drawn_on_the_undercover_background() -> None:
    with open_card(render_result_card(("Аня",), "пицца")) as card:
        assert card.getpixel((10, 10)) == background_corner(BACKGROUND_UNDERCOVER)


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
    with (
        open_card(payload) as card,
        Image.open(TEMPLATES_DIR / background_name) as background,
    ):
        box = ImageChops.difference(card, background.convert("RGB")).getbbox()
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
