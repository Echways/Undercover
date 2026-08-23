from dataclasses import dataclass
from math import cos, radians, sin
from typing import Protocol

from PIL import Image, ImageDraw, ImageFont

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
)
from undercover.media.typography import draw_tracked, fit, font, text_width
from undercover.texts import Cards


class Block(Protocol):
    @property
    def space_before(self) -> int: ...

    @property
    def height(self) -> int: ...

    def draw(self, layer: Image.Image, top: int) -> None: ...


@dataclass(frozen=True, slots=True)
class TextBlock:
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
            left = (CARD_WIDTH - text_width(self.font, line, self.tracking)) / 2
            draw_tracked(
                draw,
                (left, top + index * self.line_height),
                line,
                self.font,
                self.color,
                self.tracking,
            )


@dataclass(frozen=True, slots=True)
class CaptionBlock:
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
        span_width = text_width(self.font, self.text, self.tracking)
        left = (CARD_WIDTH - span_width) / 2
        draw_tracked(draw, (left, top), self.text, self.font, self.color, self.tracking)

        span = span_width + 2 * (CAPTION_RULE_GAP + CAPTION_RULE_LENGTH)
        if span > CONTENT_WIDTH:
            return

        middle = top + self.font.size * 0.62
        right = left + span_width
        for start, end in (
            (left - CAPTION_RULE_GAP - CAPTION_RULE_LENGTH, left - CAPTION_RULE_GAP),
            (right + CAPTION_RULE_GAP, right + CAPTION_RULE_GAP + CAPTION_RULE_LENGTH),
        ):
            draw.line((start, middle, end, middle), fill=self.color, width=CAPTION_RULE_WIDTH)


@dataclass(frozen=True, slots=True)
class StampBlock:
    text: str
    font_file: str
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
        face = font(self.font_file, self.font_size)
        width = text_width(face, self.text, self.tracking) + 2 * STAMP_PADDING_X
        height = self.font_size * 1.05 + 2 * STAMP_PADDING_Y
        return round(width), round(height)

    def _plate(self) -> Image.Image:
        scale = STAMP_SUPERSAMPLE
        width, height = (side * scale for side in self._plate_size)
        face = font(self.font_file, self.font_size * scale)
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

        _, ink_top, _, ink_bottom = face.getbbox(self.text)
        left = (width - text_width(face, self.text, tracking)) / 2
        baseline = (height - (ink_bottom - ink_top)) / 2 - ink_top
        draw_tracked(draw, (left, baseline), self.text, face, self.color, tracking)
        return plate


def caption(text: str, color: Ink, space_before: int = 0) -> CaptionBlock:
    return CaptionBlock(
        text=text,
        font=font(FONT_BOLD, CAPTION_SIZE),
        color=color,
        space_before=space_before,
    )


def owner(name: str, color: Ink) -> TextBlock:
    face, lines = fit(name, FONT_REGULAR, max_size=OWNER_SIZE, min_size=OWNER_SIZE, max_lines=1)
    return TextBlock(lines=lines, font=face, color=color)


def footnote(text: str, color: Ink, space_before: int) -> TextBlock:
    return TextBlock(
        lines=(text,),
        font=font(FONT_REGULAR, FOOTNOTE_SIZE),
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
    return TextBlock(lines=lines, font=face, color=INK, space_before=36, line_spacing=1.22)


def stamp(space_before: int = 0) -> StampBlock:
    return StampBlock(
        text=Cards.SPY_PLATE,
        font_file=FONT_BOLD,
        font_size=STAMP_TEXT_SIZE,
        color=STAMP_INK,
        fill=STAMP_FILL,
        space_before=space_before,
        tracking=STAMP_TRACKING,
    )
