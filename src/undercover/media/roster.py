from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil

from PIL import Image, ImageDraw, ImageFont

from undercover.media.layout import (
    CONTENT_LEFT,
    CONTENT_WIDTH,
    FONT_BOLD,
    ROSTER_COLUMN_GAP,
    ROSTER_LINE_SPACING,
    ROSTER_MAX_COLUMNS,
    ROSTER_MAX_SIZE,
    ROSTER_MIN_SIZE,
    ROSTER_SIZE_STEP,
    ROSTER_SPLIT_GAP,
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
    short_tag: str = ""


@dataclass(frozen=True, slots=True)
class RosterBlock:
    rows: tuple[RosterRow, ...]
    name_font: ImageFont.FreeTypeFont
    tag_font: ImageFont.FreeTypeFont
    space_before: int = 0
    columns: int = 1

    @property
    def line_height(self) -> int:
        return round(self.name_font.size * ROSTER_LINE_SPACING)

    @property
    def rows_per_column(self) -> int:
        return ceil(len(self.rows) / self.columns)

    @property
    def height(self) -> int:
        return self.line_height * self.rows_per_column

    @property
    def column_width(self) -> float:
        return (CONTENT_WIDTH - (self.columns - 1) * ROSTER_SPLIT_GAP) / self.columns

    def draw(self, layer: Image.Image, top: int) -> None:
        draw = ImageDraw.Draw(layer)
        drop = self.name_font.getmetrics()[0] - self.tag_font.getmetrics()[0]
        width = self.column_width

        for index, row in enumerate(self.rows):
            column, line = divmod(index, self.rows_per_column)
            left = CONTENT_LEFT + column * (width + ROSTER_SPLIT_GAP)
            line_top = top + line * self.line_height
            tag = self._tag(row)
            tag_width = text_width(self.tag_font, tag, ROSTER_TAG_TRACKING)
            name = shorten(row.name, self.name_font, _name_width(width, tag_width), 0)
            draw.text((left, line_top), name, font=self.name_font, fill=row.ink)
            if not tag:
                continue
            draw_tracked(
                draw,
                (left + width - tag_width, line_top + drop),
                tag,
                self.tag_font,
                row.tag_ink,
                ROSTER_TAG_TRACKING,
            )

    def _tag(self, row: RosterRow) -> str:
        if self.columns > 1 and row.short_tag:
            return row.short_tag
        return row.tag


def roster(rows: Sequence[RosterRow], budget: int, space_before: int = 0) -> RosterBlock:
    for columns in range(1, ROSTER_MAX_COLUMNS + 1):
        for size in range(ROSTER_MAX_SIZE, ROSTER_MIN_SIZE, -ROSTER_SIZE_STEP):
            block = _sized(rows, size, space_before, columns)
            if block.height <= budget:
                return block
    return _sized(rows, ROSTER_MIN_SIZE, space_before, ROSTER_MAX_COLUMNS)


def _sized(rows: Sequence[RosterRow], size: int, space_before: int, columns: int) -> RosterBlock:
    tag_size = max(round(size * ROSTER_TAG_RATIO), ROSTER_TAG_MIN_SIZE)
    return RosterBlock(
        rows=tuple(rows),
        name_font=font(FONT_BOLD, size),
        tag_font=font(FONT_BOLD, tag_size),
        space_before=space_before,
        columns=columns,
    )


def _name_width(column_width: float, tag_width: float) -> float:
    if not tag_width:
        return column_width
    return column_width - tag_width - ROSTER_COLUMN_GAP
