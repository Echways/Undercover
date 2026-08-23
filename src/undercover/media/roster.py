from collections.abc import Sequence
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from undercover.media.layout import (
    CONTENT_LEFT,
    CONTENT_RIGHT,
    CONTENT_WIDTH,
    FONT_BOLD,
    ROSTER_COLUMN_GAP,
    ROSTER_LINE_SPACING,
    ROSTER_MAX_SIZE,
    ROSTER_MIN_SIZE,
    ROSTER_SIZE_STEP,
    ROSTER_TAG_MIN_SIZE,
    ROSTER_TAG_RATIO,
    ROSTER_TAG_TRACKING,
    Ink,
)
from undercover.media.typography import draw_tracked, font, shorten, text_width


@dataclass(frozen=True, slots=True)
class RosterRow:
    name: str
    tag: str
    ink: Ink
    tag_ink: Ink


@dataclass(frozen=True, slots=True)
class RosterBlock:
    rows: tuple[RosterRow, ...]
    name_font: ImageFont.FreeTypeFont
    tag_font: ImageFont.FreeTypeFont
    space_before: int = 0

    @property
    def line_height(self) -> int:
        return round(self.name_font.size * ROSTER_LINE_SPACING)

    @property
    def height(self) -> int:
        return self.line_height * len(self.rows)

    def draw(self, layer: Image.Image, top: int) -> None:
        draw = ImageDraw.Draw(layer)
        drop = self.name_font.getmetrics()[0] - self.tag_font.getmetrics()[0]

        for index, row in enumerate(self.rows):
            line_top = top + index * self.line_height
            tag_width = text_width(self.tag_font, row.tag, ROSTER_TAG_TRACKING)
            name = shorten(row.name, self.name_font, _name_width(tag_width), 0)
            draw.text((CONTENT_LEFT, line_top), name, font=self.name_font, fill=row.ink)
            if not row.tag:
                continue
            draw_tracked(
                draw,
                (CONTENT_RIGHT - tag_width, line_top + drop),
                row.tag,
                self.tag_font,
                row.tag_ink,
                ROSTER_TAG_TRACKING,
            )


def roster(rows: Sequence[RosterRow], budget: int, space_before: int = 0) -> RosterBlock:
    for size in range(ROSTER_MAX_SIZE, ROSTER_MIN_SIZE, -ROSTER_SIZE_STEP):
        block = _sized(rows, size, space_before)
        if block.height <= budget:
            return block
    return _sized(rows, ROSTER_MIN_SIZE, space_before)


def _sized(rows: Sequence[RosterRow], size: int, space_before: int) -> RosterBlock:
    tag_size = max(round(size * ROSTER_TAG_RATIO), ROSTER_TAG_MIN_SIZE)
    return RosterBlock(
        rows=tuple(rows),
        name_font=font(FONT_BOLD, size),
        tag_font=font(FONT_BOLD, tag_size),
        space_before=space_before,
    )


def _name_width(tag_width: float) -> float:
    if not tag_width:
        return CONTENT_WIDTH
    return CONTENT_WIDTH - tag_width - ROSTER_COLUMN_GAP
