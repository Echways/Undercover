import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Final, Protocol

from PIL import Image, ImageDraw, ImageFont

from undercover.texts import Cards

RGB = tuple[int, int, int]

CARD_SIZE: Final[tuple[int, int]] = (1080, 1350)

CARD_WIDTH, CARD_HEIGHT = CARD_SIZE

TEMPLATES_DIR: Final[Path] = Path(__file__).parent / "templates"

BACKGROUND_NEUTRAL: Final = "bg_neutral.png"

BACKGROUND_UNDERCOVER: Final = "bg_undercover.png"

FONT_REGULAR: Final = "DejaVuSans.ttf"
FONT_BOLD: Final = "DejaVuSans-Bold.ttf"

SAFE_MARGIN: Final = 96

CONTENT_WIDTH: Final = CARD_WIDTH - 2 * SAFE_MARGIN

HYPHEN_BREAK: Final = re.compile(r"(?<=-)")


INK: Final[RGB] = (244, 246, 251)
INK_MUTED: Final[RGB] = (146, 158, 186)

INK_MUTED_WARM: Final[RGB] = (198, 152, 160)

PLATE_COLOR: Final[RGB] = (198, 34, 54)
PLATE_INK: Final[RGB] = (255, 246, 247)


CAPTION_SIZE: Final = 38
CAPTION_TRACKING: Final = 10

OWNER_SIZE: Final = 50
FOOTNOTE_SIZE: Final = 32
PLATE_TEXT_SIZE: Final = 68
PLATE_TRACKING: Final = 12
PLATE_PADDING_X: Final = 56
PLATE_PADDING_Y: Final = 26

HEADLINE_MAX_SIZE: Final = 120
HEADLINE_MIN_SIZE: Final = 52
HEADLINE_MAX_LINES: Final = 2

HINT_MAX_SIZE: Final = 56
HINT_MIN_SIZE: Final = 32
HINT_MAX_LINES: Final = 4

RESULT_WORD_MAX_LINES: Final = 2


@lru_cache(maxsize=None)
def _font(file_name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(TEMPLATES_DIR / file_name, size)


@lru_cache(maxsize=None)
def _background(file_name: str) -> Image.Image:
    with Image.open(TEMPLATES_DIR / file_name) as source:
        return source.convert("RGB")


def _text_width(font: ImageFont.FreeTypeFont, text: str, tracking: int) -> float:
    return font.getlength(text) + tracking * max(len(text) - 1, 0)


def _draw_text(
    draw: ImageDraw.ImageDraw,
    position: tuple[float, float],
    text: str,
    font: ImageFont.FreeTypeFont,
    color: RGB,
    tracking: int,
) -> None:
    x, y = position
    if not tracking:
        draw.text((x, y), text, font=font, fill=color)
        return
    for char in text:
        draw.text((x, y), char, font=font, fill=color)
        x += font.getlength(char) + tracking


def _split_letters(
    word: str, font: ImageFont.FreeTypeFont, max_width: float, tracking: int
) -> Iterator[str]:
    chunk = ""
    for char in word:
        if chunk and _text_width(font, chunk + char, tracking) > max_width:
            yield chunk
            chunk = char
        else:
            chunk += char
    if chunk:
        yield chunk


def _split_word(
    word: str, font: ImageFont.FreeTypeFont, max_width: float, tracking: int
) -> Iterator[str]:
    if _text_width(font, word, tracking) <= max_width:
        yield word
        return

    parts = [part for part in HYPHEN_BREAK.split(word) if part]
    if len(parts) == 1:
        yield from _split_letters(word, font, max_width, tracking)
        return

    chunk = ""
    for part in parts:
        if chunk and _text_width(font, chunk + part, tracking) > max_width:
            yield from _split_word(chunk, font, max_width, tracking)
            chunk = part
        else:
            chunk += part
    if chunk:
        yield from _split_word(chunk, font, max_width, tracking)


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_width: float, tracking: int) -> list[str]:
    lines: list[str] = []
    current = ""

    for word in text.split(" "):
        if _text_width(font, word, tracking) > max_width:
            if current:
                lines.append(current)
            *head, current = _split_word(word, font, max_width, tracking)
            lines.extend(head)
            continue

        candidate = f"{current} {word}" if current else word
        if current and _text_width(font, candidate, tracking) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate

    if current:
        lines.append(current)
    return lines


def _ellipsized(
    lines: Sequence[str],
    max_lines: int,
    font: ImageFont.FreeTypeFont,
    max_width: float,
    tracking: int,
) -> tuple[str, ...]:
    if len(lines) <= max_lines:
        return tuple(lines)

    kept = list(lines[:max_lines])
    last = kept[-1]
    while last and _text_width(font, f"{last}…", tracking) > max_width:
        last = last[:-1]
    kept[-1] = f"{last}…"
    return tuple(kept)


def _fit(
    text: str,
    font_file: str,
    *,
    max_size: int,
    min_size: int,
    max_lines: int,
    tracking: int = 0,
    max_width: float = CONTENT_WIDTH,
) -> tuple[ImageFont.FreeTypeFont, tuple[str, ...]]:
    for size in range(max_size, min_size, -4):
        font = _font(font_file, size)
        lines = _wrap(text, font, max_width, tracking)
        if len(lines) <= max_lines:
            return font, tuple(lines)

    font = _font(font_file, min_size)
    lines = _wrap(text, font, max_width, tracking)
    return font, _ellipsized(lines, max_lines, font, max_width, tracking)


class _Block(Protocol):
    @property
    def space_before(self) -> int: ...

    @property
    def height(self) -> int: ...

    def draw(self, draw: ImageDraw.ImageDraw, top: int) -> None: ...


@dataclass(frozen=True, slots=True)
class _TextBlock:
    lines: tuple[str, ...]
    font: ImageFont.FreeTypeFont
    color: RGB
    space_before: int = 0
    tracking: int = 0
    line_spacing: float = 1.3

    @property
    def line_height(self) -> int:
        return round(self.font.size * self.line_spacing)

    @property
    def height(self) -> int:
        return self.line_height * len(self.lines)

    def draw(self, draw: ImageDraw.ImageDraw, top: int) -> None:
        for index, line in enumerate(self.lines):
            left = (CARD_WIDTH - _text_width(self.font, line, self.tracking)) / 2
            _draw_text(
                draw,
                (left, top + index * self.line_height),
                line,
                self.font,
                self.color,
                self.tracking,
            )


@dataclass(frozen=True, slots=True)
class _PlateBlock:
    text: str
    font: ImageFont.FreeTypeFont
    color: RGB
    plate_color: RGB
    space_before: int = 0
    tracking: int = 0

    @property
    def height(self) -> int:
        return round(self.font.size * 1.05) + 2 * PLATE_PADDING_Y

    def draw(self, draw: ImageDraw.ImageDraw, top: int) -> None:
        text_width = _text_width(self.font, self.text, self.tracking)
        plate_width = text_width + 2 * PLATE_PADDING_X
        left = (CARD_WIDTH - plate_width) / 2

        draw.rounded_rectangle(
            (left, top, left + plate_width, top + self.height),
            radius=self.height / 2,
            fill=self.plate_color,
        )

        _, ink_top, _, ink_bottom = self.font.getbbox(self.text)
        baseline = top + (self.height - (ink_bottom - ink_top)) / 2 - ink_top
        _draw_text(
            draw,
            (left + PLATE_PADDING_X, baseline),
            self.text,
            self.font,
            self.color,
            self.tracking,
        )


def _render(background: str, blocks: Sequence[_Block]) -> bytes:
    card = _background(background).copy()
    draw = ImageDraw.Draw(card)

    top = (CARD_HEIGHT - sum(block.space_before + block.height for block in blocks)) / 2
    for block in blocks:
        top += block.space_before
        block.draw(draw, round(top))
        top += block.height

    buffer = BytesIO()
    card.save(buffer, format="PNG")
    return buffer.getvalue()


def _clean(value: str, field: str) -> str:
    text = " ".join(value.split())
    if not text:
        raise ValueError(f"{field} не может быть пустым")
    return text


def _caption(text: str, color: RGB, space_before: int = 0) -> _TextBlock:
    return _TextBlock(
        lines=(text,),
        font=_font(FONT_BOLD, CAPTION_SIZE),
        color=color,
        space_before=space_before,
        tracking=CAPTION_TRACKING,
    )


def _owner(name: str, color: RGB) -> _TextBlock:
    font, lines = _fit(name, FONT_REGULAR, max_size=OWNER_SIZE, min_size=OWNER_SIZE, max_lines=1)
    return _TextBlock(lines=lines, font=font, color=color)


def _footnote(text: str, color: RGB, space_before: int) -> _TextBlock:
    return _TextBlock(
        lines=(text,),
        font=_font(FONT_REGULAR, FOOTNOTE_SIZE),
        color=color,
        space_before=space_before,
    )


def _headline(text: str) -> _TextBlock:
    font, lines = _fit(
        text,
        FONT_BOLD,
        max_size=HEADLINE_MAX_SIZE,
        min_size=HEADLINE_MIN_SIZE,
        max_lines=HEADLINE_MAX_LINES,
    )
    return _TextBlock(lines=lines, font=font, color=INK, space_before=36, line_spacing=1.22)


def render_hidden_card(name: str) -> bytes:
    player = _clean(name, "имя игрока")
    return _render(
        BACKGROUND_NEUTRAL,
        (
            _caption(Cards.HIDDEN_CAPTION, INK_MUTED),
            _headline(player),
            _footnote(Cards.HIDDEN_FOOTNOTE, INK_MUTED, space_before=56),
        ),
    )


def render_civilian_card(name: str, word: str) -> bytes:
    player = _clean(name, "имя игрока")
    secret = _clean(word, "слово")
    return _render(
        BACKGROUND_NEUTRAL,
        (
            _owner(player, INK_MUTED),
            _caption(Cards.CIVILIAN_CAPTION, INK_MUTED, space_before=48),
            _headline(secret),
            _footnote(Cards.CIVILIAN_FOOTNOTE, INK_MUTED, space_before=56),
        ),
    )


def render_spy_card(name: str, hint: str) -> bytes:
    player = _clean(name, "имя игрока")
    clue = _clean(hint, "подсказка")
    hint_font, hint_lines = _fit(
        clue,
        FONT_REGULAR,
        max_size=HINT_MAX_SIZE,
        min_size=HINT_MIN_SIZE,
        max_lines=HINT_MAX_LINES,
    )
    return _render(
        BACKGROUND_UNDERCOVER,
        (
            _owner(player, INK_MUTED_WARM),
            _PlateBlock(
                text=Cards.SPY_PLATE,
                font=_font(FONT_BOLD, PLATE_TEXT_SIZE),
                color=PLATE_INK,
                plate_color=PLATE_COLOR,
                space_before=44,
                tracking=PLATE_TRACKING,
            ),
            _caption(Cards.SPY_CAPTION, INK_MUTED_WARM, space_before=56),
            _TextBlock(
                lines=hint_lines,
                font=hint_font,
                color=INK,
                space_before=28,
                line_spacing=1.35,
            ),
            _footnote(Cards.SPY_FOOTNOTE, INK_MUTED_WARM, space_before=56),
        ),
    )


def render_speaker_card(name: str) -> bytes:
    player = _clean(name, "имя игрока")
    return _render(
        BACKGROUND_NEUTRAL,
        (
            _caption(Cards.SPEAKER_CAPTION, INK_MUTED),
            _headline(player),
            _footnote(Cards.SPEAKER_FOOTNOTE, INK_MUTED, space_before=56),
        ),
    )


def render_result_card(spy_names: Sequence[str], word: str) -> bytes:
    if not spy_names:
        raise ValueError("список шпионов не может быть пустым")

    spies = ", ".join(_clean(name, "имя шпиона") for name in spy_names)
    secret = _clean(word, "слово")
    word_font, word_lines = _fit(
        secret,
        FONT_BOLD,
        max_size=HINT_MAX_SIZE,
        min_size=HINT_MIN_SIZE,
        max_lines=RESULT_WORD_MAX_LINES,
    )
    return _render(
        BACKGROUND_UNDERCOVER,
        (
            _PlateBlock(
                text=Cards.SPY_PLATE,
                font=_font(FONT_BOLD, PLATE_TEXT_SIZE),
                color=PLATE_INK,
                plate_color=PLATE_COLOR,
                tracking=PLATE_TRACKING,
            ),
            _caption(
                Cards.RESULT_SPIES_CAPTION if len(spy_names) > 1 else Cards.RESULT_SPY_CAPTION,
                INK_MUTED_WARM,
                space_before=56,
            ),
            _headline(spies),
            _caption(Cards.RESULT_WORD_CAPTION, INK_MUTED_WARM, space_before=48),
            _TextBlock(
                lines=word_lines,
                font=word_font,
                color=INK,
                space_before=28,
                line_spacing=1.35,
            ),
        ),
    )
