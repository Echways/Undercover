import re
from collections.abc import Iterator, Sequence
from functools import cache
from typing import Final

from PIL import ImageDraw, ImageFont

from undercover.media.layout import CONTENT_WIDTH, TEMPLATES_DIR, Ink

HYPHEN_BREAK: Final = re.compile(r"(?<=-)")
ELLIPSIS: Final = "…"


def plain(value: str, field: str) -> str:
    text = " ".join(value.split())
    if not text:
        raise ValueError(f"{field} не может быть пустым")
    return text


@cache
def font(file_name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(TEMPLATES_DIR / file_name, size)


def text_width(face: ImageFont.FreeTypeFont, text: str, tracking: int) -> float:
    return face.getlength(text) + tracking * max(len(text) - 1, 0)


def draw_tracked(
    draw: ImageDraw.ImageDraw,
    position: tuple[float, float],
    text: str,
    face: ImageFont.FreeTypeFont,
    color: Ink,
    tracking: int,
) -> None:
    x, y = position
    if not tracking:
        draw.text((x, y), text, font=face, fill=color)
        return
    for char in text:
        draw.text((x, y), char, font=face, fill=color)
        x += face.getlength(char) + tracking


def wrap(text: str, face: ImageFont.FreeTypeFont, max_width: float, tracking: int) -> list[str]:
    lines: list[str] = []
    current = ""

    for word in text.split(" "):
        if text_width(face, word, tracking) > max_width:
            if current:
                lines.append(current)
            *head, current = _split_word(word, face, max_width, tracking)
            lines.extend(head)
            continue

        candidate = f"{current} {word}" if current else word
        if current and text_width(face, candidate, tracking) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate

    if current:
        lines.append(current)
    return lines


def shorten(text: str, face: ImageFont.FreeTypeFont, max_width: float, tracking: int) -> str:
    if text_width(face, text, tracking) <= max_width:
        return text
    return _tailed(text, face, max_width, tracking)


def fit(
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
        face = font(font_file, size)
        lines = wrap(text, face, max_width, tracking)
        if len(lines) <= max_lines:
            return face, tuple(lines)

    face = font(font_file, min_size)
    lines = wrap(text, face, max_width, tracking)
    return face, _ellipsized(lines, max_lines, face, max_width, tracking)


def _split_letters(
    word: str, face: ImageFont.FreeTypeFont, max_width: float, tracking: int
) -> Iterator[str]:
    chunk = ""
    for char in word:
        if chunk and text_width(face, chunk + char, tracking) > max_width:
            yield chunk
            chunk = char
        else:
            chunk += char
    if chunk:
        yield chunk


def _split_word(
    word: str, face: ImageFont.FreeTypeFont, max_width: float, tracking: int
) -> Iterator[str]:
    if text_width(face, word, tracking) <= max_width:
        yield word
        return

    parts = [part for part in HYPHEN_BREAK.split(word) if part]
    if len(parts) == 1:
        yield from _split_letters(word, face, max_width, tracking)
        return

    chunk = ""
    for part in parts:
        if chunk and text_width(face, chunk + part, tracking) > max_width:
            yield from _split_word(chunk, face, max_width, tracking)
            chunk = part
        else:
            chunk += part
    if chunk:
        yield from _split_word(chunk, face, max_width, tracking)


def _tailed(text: str, face: ImageFont.FreeTypeFont, max_width: float, tracking: int) -> str:
    kept = text
    while kept and text_width(face, kept + ELLIPSIS, tracking) > max_width:
        kept = kept[:-1]
    return kept + ELLIPSIS


def _ellipsized(
    lines: Sequence[str],
    max_lines: int,
    face: ImageFont.FreeTypeFont,
    max_width: float,
    tracking: int,
) -> tuple[str, ...]:
    if len(lines) <= max_lines:
        return tuple(lines)

    kept = list(lines[:max_lines])
    kept[-1] = _tailed(kept[-1], face, max_width, tracking)
    return tuple(kept)
