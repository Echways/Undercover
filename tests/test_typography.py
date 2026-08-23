import pytest
from PIL import Image, ImageDraw

from undercover.media.layout import (
    CARD_SIZE,
    CONTENT_WIDTH,
    FONT_BOLD,
    FONT_REGULAR,
    TEMPLATES_DIR,
    Ink,
    Typeface,
)
from undercover.media.typography import Face, draw_text, fit, font, stack

TYPEFACES: tuple[Typeface, ...] = (FONT_BOLD, FONT_REGULAR)
BUNDLED: tuple[str, ...] = tuple(
    sorted(asset.name for asset in TEMPLATES_DIR.iterdir() if asset.suffix in {".otf", ".ttf"})
)

PEN = (200.0, 500.0)
WHITE: Ink = (255, 255, 255)
INK_TOLERANCE = 2
CAP_TOLERANCE = 2


def painted(face: Face, text: str, tracking: int = 0) -> tuple[int, int, int, int]:
    layer = Image.new("RGB", CARD_SIZE, (0, 0, 0))
    draw_text(ImageDraw.Draw(layer), PEN, text, face, WHITE, tracking)
    box = layer.getbbox()
    assert box is not None
    return box


@pytest.mark.parametrize("typeface", TYPEFACES)
@pytest.mark.parametrize("size", [24, 44, 72, 120])
def test_a_typeface_renders_the_cap_height_the_layout_asks_for(
    typeface: Typeface, size: int
) -> None:
    face = font(typeface, size)

    assert face.cap_height == pytest.approx(size * typeface.cap_ratio, abs=CAP_TOLERANCE)


@pytest.mark.parametrize("file_name", BUNDLED)
def test_any_bundled_font_lands_on_the_same_cap_height(file_name: str) -> None:
    face = font(Typeface(file=file_name, cap_ratio=FONT_BOLD.cap_ratio), 100)

    assert face.cap_height == pytest.approx(100 * FONT_BOLD.cap_ratio, abs=CAP_TOLERANCE)


@pytest.mark.parametrize("typeface", TYPEFACES)
def test_the_box_predicts_the_ink_that_lands_on_the_card(typeface: Typeface) -> None:
    face = font(typeface, 72)
    box = face.box("Аня-Ру")

    left, top, right, bottom = painted(face, "Аня-Ру")

    assert left >= PEN[0] + box.left - INK_TOLERANCE
    assert top >= PEN[1] + box.top - INK_TOLERANCE
    assert right <= PEN[0] + box.right + INK_TOLERANCE
    assert bottom <= PEN[1] + box.bottom + INK_TOLERANCE


def test_the_box_counts_tracking_in_the_width() -> None:
    face = font(FONT_BOLD, 60)

    tracked = painted(face, "ШПИОН", 12)
    plain_text = painted(face, "ШПИОН")

    assert tracked[2] - tracked[0] > plain_text[2] - plain_text[0]
    assert tracked[2] - tracked[0] <= face.width("ШПИОН", 12) + INK_TOLERANCE


@pytest.mark.parametrize("typeface", TYPEFACES)
def test_a_stack_reserves_the_ink_that_it_paints(typeface: Typeface) -> None:
    face = font(typeface, 48)
    lines = ("Рудольф", "Аня")
    line_height = face.line_height(1.3)
    reserved = stack(face, [face.box(line) for line in lines], line_height, len(lines))

    layer = Image.new("RGB", CARD_SIZE, (0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for index, line in enumerate(lines):
        draw_text(draw, (100, reserved.baseline + index * line_height), line, face, WHITE)
    box = layer.getbbox()

    assert box is not None
    assert box[1] >= 0
    assert box[3] <= reserved.height


def test_a_face_of_the_same_size_is_reused() -> None:
    assert font(FONT_BOLD, 60) is font(FONT_BOLD, 60)


def test_fit_keeps_a_long_word_whole_by_shrinking_it() -> None:
    face, lines = fit("электрочайник", FONT_BOLD, max_size=120, min_size=52, max_lines=2)

    assert lines == ("электрочайник",)
    assert face.size < 120


def test_fit_falls_back_to_breaking_a_word_that_never_fits() -> None:
    word = "Аполлинария" * 3
    face, lines = fit(word, FONT_BOLD, max_size=120, min_size=52, max_lines=2)

    assert "".join(lines) == word
    assert face.width(word) > CONTENT_WIDTH
