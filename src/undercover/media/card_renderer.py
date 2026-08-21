import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from functools import cache
from io import BytesIO
from math import cos, radians, sin
from pathlib import Path
from typing import Final, Protocol

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from undercover.texts import Cards

RGB = tuple[int, int, int]
RGBA = tuple[int, int, int, int]
Ink = RGB | RGBA

CARD_SIZE: Final[tuple[int, int]] = (1080, 1350)

CARD_WIDTH, CARD_HEIGHT = CARD_SIZE

CARD_FORMAT: Final = "JPEG"
CARD_SUFFIX: Final = "jpg"
CARD_QUALITY: Final = 92

TEMPLATES_DIR: Final[Path] = Path(__file__).parent / "templates"

BACKGROUND_NEUTRAL: Final = "bg_neutral.jpg"

BACKGROUND_UNDERCOVER: Final = "bg_undercover.jpg"

FONT_REGULAR: Final = "regular.ttf"
FONT_BOLD: Final = "bold.otf"

SAFE_MARGIN: Final = 96

GLOW_BLEED: Final = 32

CONTENT_WIDTH: Final = CARD_WIDTH - 2 * (SAFE_MARGIN + GLOW_BLEED)

LAMP_CENTER: Final = round(CARD_HEIGHT * 0.46)

HYPHEN_BREAK: Final = re.compile(r"(?<=-)")


INK: Final[RGB] = (247, 248, 252)
INK_MUTED: Final[RGB] = (152, 172, 208)

INK_MUTED_WARM: Final[RGB] = (214, 156, 158)

GLOW_COLD: Final[RGB] = (74, 122, 194)
GLOW_WARM: Final[RGB] = (186, 58, 60)

SHADOW_COLOR: Final[RGB] = (0, 0, 0)
SHADOW_BLUR: Final = 8.0
SHADOW_OFFSET: Final[tuple[int, int]] = (0, 5)
SHADOW_OPACITY: Final = 0.85

GLOW_BLUR: Final = 7.0
GLOW_OPACITY: Final = 0.45


CAPTION_SIZE: Final = 36
CAPTION_TRACKING: Final = 11
CAPTION_RULE_LENGTH: Final = 64
CAPTION_RULE_GAP: Final = 26
CAPTION_RULE_WIDTH: Final = 2

OWNER_SIZE: Final = 50
FOOTNOTE_SIZE: Final = 32

STAMP_TEXT_SIZE: Final = 60
STAMP_TRACKING: Final = 10
STAMP_PADDING_X: Final = 46
STAMP_PADDING_Y: Final = 24
STAMP_ANGLE: Final = 3.0
STAMP_BORDER: Final = 5
STAMP_INSET: Final = 10
STAMP_INNER_BORDER: Final = 2
STAMP_SUPERSAMPLE: Final = 2
STAMP_INK: Final[RGBA] = (255, 244, 245, 236)
STAMP_FILL: Final[RGBA] = (28, 6, 10, 104)

WORDMARK_SIZE: Final = 26
WORDMARK_TRACKING: Final = 16
WORDMARK_INK: Final[RGBA] = (238, 240, 248, 120)

HEADLINE_MAX_SIZE: Final = 120
HEADLINE_MIN_SIZE: Final = 52
HEADLINE_MAX_LINES: Final = 2

HINT_MAX_SIZE: Final = 56
HINT_MIN_SIZE: Final = 32
HINT_MAX_LINES: Final = 4

RESULT_WORD_MAX_LINES: Final = 2


@cache
def _font(file_name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(TEMPLATES_DIR / file_name, size)


@cache
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
    color: Ink,
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

    def draw(self, layer: Image.Image, top: int) -> None: ...


@dataclass(frozen=True, slots=True)
class _TextBlock:
    lines: tuple[str, ...]
    font: ImageFont.FreeTypeFont
    color: Ink
    space_before: int = 0
    tracking: int = 0
    line_spacing: float = 1.3

    @property
    def line_height(self) -> int:
        return round(self.font.size * self.line_spacing)

    @property
    def height(self) -> int:
        return self.line_height * len(self.lines)

    def draw(self, layer: Image.Image, top: int) -> None:
        draw = ImageDraw.Draw(layer)
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
class _CaptionBlock:
    """Разряженный капс, подхваченный с двух сторон тонкими линейками."""

    text: str
    font: ImageFont.FreeTypeFont
    color: Ink
    space_before: int = 0
    tracking: int = CAPTION_TRACKING

    @property
    def height(self) -> int:
        return round(self.font.size * 1.3)

    def draw(self, layer: Image.Image, top: int) -> None:
        draw = ImageDraw.Draw(layer)
        text_width = _text_width(self.font, self.text, self.tracking)
        left = (CARD_WIDTH - text_width) / 2
        _draw_text(draw, (left, top), self.text, self.font, self.color, self.tracking)

        span = text_width + 2 * (CAPTION_RULE_GAP + CAPTION_RULE_LENGTH)
        if span > CONTENT_WIDTH:
            return

        middle = top + self.font.size * 0.62
        right = left + text_width
        for start, end in (
            (left - CAPTION_RULE_GAP - CAPTION_RULE_LENGTH, left - CAPTION_RULE_GAP),
            (right + CAPTION_RULE_GAP, right + CAPTION_RULE_GAP + CAPTION_RULE_LENGTH),
        ):
            draw.line((start, middle, end, middle), fill=self.color, width=CAPTION_RULE_WIDTH)


@dataclass(frozen=True, slots=True)
class _StampBlock:
    text: str
    font_file: str
    font_size: int
    color: Ink
    fill: RGBA
    space_before: int = 0
    tracking: int = 0

    @property
    def _plate_size(self) -> tuple[int, int]:
        font = _font(self.font_file, self.font_size)
        width = _text_width(font, self.text, self.tracking) + 2 * STAMP_PADDING_X
        height = self.font_size * 1.05 + 2 * STAMP_PADDING_Y
        return round(width), round(height)

    @property
    def height(self) -> int:
        width, height = self._plate_size
        angle = radians(STAMP_ANGLE)
        return round(width * abs(sin(angle)) + height * cos(angle))

    def draw(self, layer: Image.Image, top: int) -> None:
        stamp = self._plate().rotate(STAMP_ANGLE, resample=Image.Resampling.BICUBIC, expand=True)
        stamp = stamp.resize(
            (stamp.width // STAMP_SUPERSAMPLE, stamp.height // STAMP_SUPERSAMPLE),
            Image.Resampling.LANCZOS,
        )
        layer.alpha_composite(stamp, ((CARD_WIDTH - stamp.width) // 2, top))

    def _plate(self) -> Image.Image:
        scale = STAMP_SUPERSAMPLE
        width, height = (side * scale for side in self._plate_size)
        font = _font(self.font_file, self.font_size * scale)
        tracking = self.tracking * scale

        plate = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(plate)
        draw.rectangle(
            (0, 0, width - 1, height - 1),
            fill=self.fill,
            outline=self.color,
            width=STAMP_BORDER * scale,
        )
        inset = (STAMP_BORDER + STAMP_INSET) * scale
        draw.rectangle(
            (inset, inset, width - 1 - inset, height - 1 - inset),
            outline=self.color,
            width=STAMP_INNER_BORDER * scale,
        )

        _, ink_top, _, ink_bottom = font.getbbox(self.text)
        left = (width - _text_width(font, self.text, tracking)) / 2
        baseline = (height - (ink_bottom - ink_top)) / 2 - ink_top
        _draw_text(draw, (left, baseline), self.text, font, self.color, tracking)
        return plate


def _stack_top(total: int) -> float:
    limit = SAFE_MARGIN + GLOW_BLEED
    available = CARD_HEIGHT - 2 * limit
    if total >= available:
        return (CARD_HEIGHT - total) / 2
    return min(max(LAMP_CENTER - total / 2, limit), limit + available - total)


def _bleed(alpha: Image.Image, blur: float, offset: tuple[int, int], opacity: float) -> Image.Image:
    spread = alpha.filter(ImageFilter.GaussianBlur(blur)).point(
        lambda level: round(level * opacity)
    )
    if offset == (0, 0):
        return spread

    shifted = Image.new("L", CARD_SIZE, 0)
    shifted.paste(spread, offset)
    return shifted


def _wordmark(layer: Image.Image) -> None:
    font = _font(FONT_BOLD, WORDMARK_SIZE)
    width = _text_width(font, Cards.SPY_PLATE, WORDMARK_TRACKING)
    _draw_text(
        ImageDraw.Draw(layer),
        ((CARD_WIDTH - width) / 2, CARD_HEIGHT - SAFE_MARGIN - GLOW_BLEED - WORDMARK_SIZE),
        Cards.SPY_PLATE,
        font,
        WORDMARK_INK,
        WORDMARK_TRACKING,
    )


def _render(background: str, glow: RGB, blocks: Sequence[_Block]) -> bytes:
    content = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))

    top = _stack_top(sum(block.space_before + block.height for block in blocks))
    for block in blocks:
        top += block.space_before
        block.draw(content, round(top))
        top += block.height
    _wordmark(content)

    card = _background(background).copy()
    ink = content.getchannel("A")
    card.paste(
        Image.new("RGB", CARD_SIZE, SHADOW_COLOR),
        mask=_bleed(ink, SHADOW_BLUR, SHADOW_OFFSET, SHADOW_OPACITY),
    )
    card.paste(Image.new("RGB", CARD_SIZE, glow), mask=_bleed(ink, GLOW_BLUR, (0, 0), GLOW_OPACITY))
    card = Image.alpha_composite(card.convert("RGBA"), content).convert("RGB")

    buffer = BytesIO()
    card.save(buffer, format=CARD_FORMAT, quality=CARD_QUALITY, subsampling=0, optimize=True)
    return buffer.getvalue()


def _clean(value: str, field: str) -> str:
    text = " ".join(value.split())
    if not text:
        raise ValueError(f"{field} не может быть пустым")
    return text


def _caption(text: str, color: Ink, space_before: int = 0) -> _CaptionBlock:
    return _CaptionBlock(
        text=text,
        font=_font(FONT_BOLD, CAPTION_SIZE),
        color=color,
        space_before=space_before,
    )


def _owner(name: str, color: Ink) -> _TextBlock:
    font, lines = _fit(name, FONT_REGULAR, max_size=OWNER_SIZE, min_size=OWNER_SIZE, max_lines=1)
    return _TextBlock(lines=lines, font=font, color=color)


def _footnote(text: str, color: Ink, space_before: int) -> _TextBlock:
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


def _stamp(space_before: int = 0) -> _StampBlock:
    return _StampBlock(
        text=Cards.SPY_PLATE,
        font_file=FONT_BOLD,
        font_size=STAMP_TEXT_SIZE,
        color=STAMP_INK,
        fill=STAMP_FILL,
        space_before=space_before,
        tracking=STAMP_TRACKING,
    )


def render_hidden_card(name: str) -> bytes:
    player = _clean(name, "имя игрока")
    return _render(
        BACKGROUND_NEUTRAL,
        GLOW_COLD,
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
        GLOW_COLD,
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
        GLOW_WARM,
        (
            _owner(player, INK_MUTED_WARM),
            _stamp(space_before=44),
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
        GLOW_COLD,
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
        GLOW_WARM,
        (
            _stamp(),
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
