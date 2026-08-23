import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from functools import cache
from typing import Final

from PIL import ImageDraw, ImageFont

from undercover.media.layout import CARD_WIDTH, CONTENT_WIDTH, TEMPLATES_DIR, Ink, Typeface

HYPHEN_BREAK: Final = re.compile(r"(?<=-)")
ELLIPSIS: Final = "…"
CAP_SAMPLE: Final = "H"
SIZE_STEP: Final = 4
PROBE_SIZE: Final = 256


def plain(value: str, field: str) -> str:
    text = " ".join(value.split())
    if not text:
        raise ValueError(f"{field} не может быть пустым")
    return text


@dataclass(frozen=True, slots=True)
class Box:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top


@dataclass(frozen=True, slots=True)
class Face:
    glyphs: ImageFont.FreeTypeFont
    size: int
    cap_height: float

    def box(self, text: str, tracking: int = 0) -> Box:
        left, top, right, bottom = self.glyphs.getbbox(text)
        origin = self.glyphs.getmetrics()[0]
        return Box(left, top - origin, right + tracking * _gaps(text), bottom - origin)

    def width(self, text: str, tracking: int = 0) -> float:
        return self.box(text, tracking).width

    def line_height(self, spacing: float) -> int:
        return round(self.size * spacing)

    def baseline(self, line_height: float) -> float:
        return (line_height + self.cap_height) / 2

    def centered(self, text: str, tracking: int = 0, span: float = CARD_WIDTH) -> float:
        box = self.box(text, tracking)
        return (span - box.width) / 2 - box.left

    def left_at(self, edge: float, text: str, tracking: int = 0) -> float:
        return edge - self.box(text, tracking).left

    def right_at(self, edge: float, text: str, tracking: int = 0) -> float:
        return edge - self.box(text, tracking).right


@dataclass(frozen=True, slots=True)
class Stack:
    baseline: float
    height: int


def stack(face: Face, boxes: Sequence[Box], line_height: int, lines: int) -> Stack:
    top = min((box.top for box in boxes), default=0.0)
    bottom = max((box.bottom for box in boxes), default=0.0)
    baseline = max(face.baseline(line_height), -top)
    reserved = max(baseline + bottom + line_height * (lines - 1), line_height * lines)
    return Stack(baseline=baseline, height=round(reserved))


@cache
def font(typeface: Typeface, size: int) -> Face:
    glyphs = _glyphs(typeface.file, _pixels(typeface, size))
    return Face(glyphs=glyphs, size=size, cap_height=_cap_height(glyphs))


def draw_text(
    draw: ImageDraw.ImageDraw,
    position: tuple[float, float],
    text: str,
    face: Face,
    color: Ink,
    tracking: int = 0,
) -> None:
    x, baseline = position
    if not tracking:
        draw.text((x, baseline), text, font=face.glyphs, fill=color, anchor="ls")
        return
    for char in text:
        draw.text((x, baseline), char, font=face.glyphs, fill=color, anchor="ls")
        x += face.glyphs.getlength(char) + tracking


def wrap(text: str, face: Face, max_width: float, tracking: int) -> list[str]:
    lines: list[str] = []
    current = ""

    for word in text.split(" "):
        if face.width(word, tracking) > max_width:
            if current:
                lines.append(current)
            *head, current = _split_word(word, face, max_width, tracking)
            lines.extend(head)
            continue

        candidate = f"{current} {word}" if current else word
        if current and face.width(candidate, tracking) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate

    if current:
        lines.append(current)
    return lines


def shorten(text: str, face: Face, max_width: float, tracking: int) -> str:
    if face.width(text, tracking) <= max_width:
        return text
    return _tailed(text, face, max_width, tracking)


def fit(
    text: str,
    typeface: Typeface,
    *,
    max_size: int,
    min_size: int,
    max_lines: int,
    tracking: int = 0,
    max_width: float = CONTENT_WIDTH,
) -> tuple[Face, tuple[str, ...]]:
    words = text.split(" ")
    crammed: tuple[Face, tuple[str, ...]] | None = None

    for size in range(max_size, min_size, -SIZE_STEP):
        face = font(typeface, size)
        lines = wrap(text, face, max_width, tracking)
        if len(lines) > max_lines:
            continue
        if all(face.width(word, tracking) <= max_width for word in words):
            return face, tuple(lines)
        if crammed is None:
            crammed = (face, tuple(lines))

    if crammed is not None:
        return crammed

    face = font(typeface, min_size)
    lines = wrap(text, face, max_width, tracking)
    return face, _ellipsized(lines, max_lines, face, max_width, tracking)


def _gaps(text: str) -> int:
    return max(len(text) - 1, 0)


@cache
def _glyphs(file_name: str, pixels: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(TEMPLATES_DIR / file_name, pixels)


def _cap_height(glyphs: ImageFont.FreeTypeFont) -> float:
    return glyphs.getmetrics()[0] - glyphs.getbbox(CAP_SAMPLE)[1]


@cache
def _cap_ratio(file_name: str) -> float:
    return _cap_height(_glyphs(file_name, PROBE_SIZE)) / PROBE_SIZE


def _pixels(typeface: Typeface, size: int) -> int:
    return max(round(size * typeface.cap_ratio / _cap_ratio(typeface.file)), 1)


def _split_letters(word: str, face: Face, max_width: float, tracking: int) -> Iterator[str]:
    chunk = ""
    for char in word:
        if chunk and face.width(chunk + char, tracking) > max_width:
            yield chunk
            chunk = char
        else:
            chunk += char
    if chunk:
        yield chunk


def _split_word(word: str, face: Face, max_width: float, tracking: int) -> Iterator[str]:
    if face.width(word, tracking) <= max_width:
        yield word
        return

    parts = [part for part in HYPHEN_BREAK.split(word) if part]
    if len(parts) == 1:
        yield from _split_letters(word, face, max_width, tracking)
        return

    chunk = ""
    for part in parts:
        if chunk and face.width(chunk + part, tracking) > max_width:
            yield from _split_word(chunk, face, max_width, tracking)
            chunk = part
        else:
            chunk += part
    if chunk:
        yield from _split_word(chunk, face, max_width, tracking)


def _tailed(text: str, face: Face, max_width: float, tracking: int) -> str:
    kept = text
    while kept and face.width(kept + ELLIPSIS, tracking) > max_width:
        kept = kept[:-1]
    return kept + ELLIPSIS


def _ellipsized(
    lines: Sequence[str],
    max_lines: int,
    face: Face,
    max_width: float,
    tracking: int,
) -> tuple[str, ...]:
    if len(lines) <= max_lines:
        return tuple(lines)

    kept = list(lines[:max_lines])
    kept[-1] = _tailed(kept[-1], face, max_width, tracking)
    return tuple(kept)
