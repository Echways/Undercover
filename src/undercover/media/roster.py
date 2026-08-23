from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil

from PIL import Image, ImageDraw

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
from undercover.media.typography import Face, Stack, draw_text, font, shorten, stack


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
    name_face: Face
    tag_face: Face
    space_before: int = 0
    columns: int = 1

    @property
    def line_height(self) -> int:
        return self.name_face.line_height(ROSTER_LINE_SPACING)

    @property
    def rows_per_column(self) -> int:
        return ceil(len(self.rows) / self.columns)

    @property
    def height(self) -> int:
        return self._stack.height

    @property
    def column_width(self) -> float:
        return (CONTENT_WIDTH - (self.columns - 1) * ROSTER_SPLIT_GAP) / self.columns

    def draw(self, layer: Image.Image, top: int) -> None:
        draw = ImageDraw.Draw(layer)
        width = self.column_width
        first = top + self._stack.baseline

        for index, row in enumerate(self.rows):
            column, line = divmod(index, self.rows_per_column)
            left = CONTENT_LEFT + column * (width + ROSTER_SPLIT_GAP)
            baseline = first + line * self.line_height
            tag = self._tag(row)
            tag_width = self.tag_face.width(tag, ROSTER_TAG_TRACKING)
            name = shorten(row.name, self.name_face, _name_width(width, tag_width), 0)
            draw_text(
                draw,
                (self.name_face.left_at(left, name), baseline),
                name,
                self.name_face,
                row.ink,
            )
            if not tag:
                continue
            draw_text(
                draw,
                (self.tag_face.right_at(left + width, tag, ROSTER_TAG_TRACKING), baseline),
                tag,
                self.tag_face,
                row.tag_ink,
                ROSTER_TAG_TRACKING,
            )

    @property
    def _stack(self) -> Stack:
        tags = [self._tag(row) for row in self.rows]
        boxes = [self.name_face.box(row.name) for row in self.rows]
        boxes += [self.tag_face.box(tag) for tag in tags if tag]
        return stack(self.name_face, boxes, self.line_height, self.rows_per_column)

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
        name_face=font(FONT_BOLD, size),
        tag_face=font(FONT_BOLD, tag_size),
        space_before=space_before,
        columns=columns,
    )


def _name_width(column_width: float, tag_width: float) -> float:
    if not tag_width:
        return column_width
    return column_width - tag_width - ROSTER_COLUMN_GAP
