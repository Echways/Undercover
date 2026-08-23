from dataclasses import dataclass
from math import cos, radians, sin
from typing import Final, Protocol

from PIL import Image, ImageDraw

from undercover.media.layout import (
    CAPTION_RULE_GAP,
    CAPTION_RULE_LENGTH,
    CAPTION_RULE_WIDTH,
    CAPTION_SIZE,
    CAPTION_TRACKING,
    CARD_WIDTH,
    CONTENT_WIDTH,
    FONT_BOLD,
    FONT_REGULAR,
    FOOTNOTE_SIZE,
    HEADLINE_MAX_LINES,
    HEADLINE_MAX_SIZE,
    HEADLINE_MIN_SIZE,
    INK,
    OWNER_SIZE,
    RGBA,
    STAMP_ANGLE,
    STAMP_BORDER,
    STAMP_FILL,
    STAMP_INK,
    STAMP_INNER_BORDER,
    STAMP_INSET,
    STAMP_PADDING_X,
    STAMP_PADDING_Y,
    STAMP_SUPERSAMPLE,
    STAMP_TEXT_SIZE,
    STAMP_TRACKING,
    Ink,
    Typeface,
)
from undercover.media.typography import Face, Stack, draw_text, fit, font, stack
from undercover.texts import Cards

CAPTION_LINE_SPACING: Final = 1.3


class Block(Protocol):
    @property
    def space_before(self) -> int: ...

    @property
    def height(self) -> int: ...

    def draw(self, layer: Image.Image, top: int) -> None: ...


@dataclass(frozen=True, slots=True)
class TextBlock:
    lines: tuple[str, ...]
    face: Face
    color: Ink
    space_before: int = 0
    tracking: int = 0
    line_spacing: float = 1.3

    @property
    def line_height(self) -> int:
        return self.face.line_height(self.line_spacing)

    @property
    def height(self) -> int:
        return self._stack.height

    def draw(self, layer: Image.Image, top: int) -> None:
        draw = ImageDraw.Draw(layer)
        baseline = top + self._stack.baseline
        for index, line in enumerate(self.lines):
            draw_text(
                draw,
                (self.face.centered(line, self.tracking), baseline + index * self.line_height),
                line,
                self.face,
                self.color,
                self.tracking,
            )

    @property
    def _stack(self) -> Stack:
        boxes = [self.face.box(line, self.tracking) for line in self.lines]
        return stack(self.face, boxes, self.line_height, len(self.lines))


@dataclass(frozen=True, slots=True)
class CaptionBlock:
    text: str
    face: Face
    color: Ink
    space_before: int = 0
    tracking: int = CAPTION_TRACKING

    @property
    def height(self) -> int:
        return self._stack.height

    def draw(self, layer: Image.Image, top: int) -> None:
        draw = ImageDraw.Draw(layer)
        baseline = top + self._stack.baseline
        span_width = self.face.width(self.text, self.tracking)
        draw_text(
            draw,
            (self.face.centered(self.text, self.tracking), baseline),
            self.text,
            self.face,
            self.color,
            self.tracking,
        )

        span = span_width + 2 * (CAPTION_RULE_GAP + CAPTION_RULE_LENGTH)
        if span > CONTENT_WIDTH:
            return

        middle = baseline - self.face.cap_height / 2
        left = (CARD_WIDTH - span_width) / 2
        right = left + span_width
        for start, end in (
            (left - CAPTION_RULE_GAP - CAPTION_RULE_LENGTH, left - CAPTION_RULE_GAP),
            (right + CAPTION_RULE_GAP, right + CAPTION_RULE_GAP + CAPTION_RULE_LENGTH),
        ):
            draw.line((start, middle, end, middle), fill=self.color, width=CAPTION_RULE_WIDTH)

    @property
    def _stack(self) -> Stack:
        line_height = self.face.line_height(CAPTION_LINE_SPACING)
        return stack(self.face, [self.face.box(self.text, self.tracking)], line_height, 1)


@dataclass(frozen=True, slots=True)
class StampBlock:
    text: str
    typeface: Typeface
    font_size: int
    color: Ink
    fill: RGBA
    space_before: int = 0
    tracking: int = 0

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

    @property
    def _plate_size(self) -> tuple[int, int]:
        face = font(self.typeface, self.font_size)
        width = face.width(self.text, self.tracking) + 2 * STAMP_PADDING_X
        return round(width), round(face.cap_height + 2 * STAMP_PADDING_Y)

    def _plate(self) -> Image.Image:
        scale = STAMP_SUPERSAMPLE
        width, height = (side * scale for side in self._plate_size)
        face = font(self.typeface, self.font_size * scale)
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

        position = (face.centered(self.text, tracking, width), face.baseline(height))
        draw_text(draw, position, self.text, face, self.color, tracking)
        return plate


def caption(text: str, color: Ink, space_before: int = 0, size: int = CAPTION_SIZE) -> CaptionBlock:
    return CaptionBlock(
        text=text,
        face=font(FONT_BOLD, size),
        color=color,
        space_before=space_before,
    )


def owner(name: str, color: Ink) -> TextBlock:
    face, lines = fit(name, FONT_REGULAR, max_size=OWNER_SIZE, min_size=OWNER_SIZE, max_lines=1)
    return TextBlock(lines=lines, face=face, color=color)


def footnote(text: str, color: Ink, space_before: int, size: int = FOOTNOTE_SIZE) -> TextBlock:
    return TextBlock(
        lines=(text,),
        face=font(FONT_REGULAR, size),
        color=color,
        space_before=space_before,
    )


def headline(text: str) -> TextBlock:
    face, lines = fit(
        text,
        FONT_BOLD,
        max_size=HEADLINE_MAX_SIZE,
        min_size=HEADLINE_MIN_SIZE,
        max_lines=HEADLINE_MAX_LINES,
    )
    return TextBlock(lines=lines, face=face, color=INK, space_before=36, line_spacing=1.22)


def stamp(space_before: int = 0) -> StampBlock:
    return StampBlock(
        text=Cards.SPY_PLATE,
        typeface=FONT_BOLD,
        font_size=STAMP_TEXT_SIZE,
        color=STAMP_INK,
        fill=STAMP_FILL,
        space_before=space_before,
        tracking=STAMP_TRACKING,
    )
