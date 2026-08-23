from PIL import Image

from undercover.media.layout import (
    CARD_SIZE,
    CONTENT_LEFT,
    CONTENT_RIGHT,
    INK,
    ROSTER_COLUMN_GAP,
    ROSTER_MAX_SIZE,
    ROSTER_MIN_SIZE,
    ROSTER_SPY_INK,
    ROSTER_TAG_TRACKING,
)
from undercover.media.roster import RosterRow, roster
from undercover.media.typography import text_width

SPY_TAG = "ШПИОН · 1-Й ВЫЛЕТ"


def rows(count: int, name: str = "Аня") -> tuple[RosterRow, ...]:
    return tuple(
        RosterRow(name=f"{name} {index}", tag=SPY_TAG, ink=INK, tag_ink=ROSTER_SPY_INK)
        for index in range(count)
    )


def painted(block: object) -> Image.Image:
    layer = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    assert hasattr(block, "draw")
    block.draw(layer, 0)
    return layer


def test_a_short_roster_keeps_the_largest_size() -> None:
    assert roster(rows(4), budget=1000).name_font.size == ROSTER_MAX_SIZE


def test_a_crowded_roster_shrinks_to_fit_the_budget() -> None:
    block = roster(rows(16), budget=600)

    assert block.height <= 600
    assert block.name_font.size < ROSTER_MAX_SIZE


def test_an_impossible_budget_stops_at_the_smallest_size() -> None:
    assert roster(rows(16), budget=1).name_font.size == ROSTER_MIN_SIZE


def test_the_block_reserves_exactly_what_it_paints() -> None:
    block = roster(rows(8), budget=1000)

    box = painted(block).getchannel("A").getbbox()

    assert box is not None
    assert box[3] <= block.height


def test_every_row_stays_inside_the_content_column() -> None:
    block = roster(rows(16, name="Аполлинария-Иннокентия"), budget=900)

    box = painted(block).getchannel("A").getbbox()

    assert box is not None
    assert box[0] >= CONTENT_LEFT
    assert box[2] <= CONTENT_RIGHT


def test_a_long_name_leaves_the_gap_before_the_tag_empty() -> None:
    block = roster(
        (RosterRow(name="Аполлинария" * 5, tag=SPY_TAG, ink=INK, tag_ink=ROSTER_SPY_INK),),
        budget=1000,
    )
    tag_left = CONTENT_RIGHT - text_width(block.tag_font, SPY_TAG, ROSTER_TAG_TRACKING)

    gap = painted(block).crop(
        (round(tag_left - ROSTER_COLUMN_GAP), 0, round(tag_left), block.height)
    )

    assert gap.getchannel("A").getbbox() is None


def test_a_row_without_a_tag_uses_the_whole_column() -> None:
    wide = roster((RosterRow(name="Аполлинария" * 5, tag="", ink=INK, tag_ink=INK),), budget=1000)
    narrow = roster(
        (RosterRow(name="Аполлинария" * 5, tag=SPY_TAG, ink=INK, tag_ink=ROSTER_SPY_INK),),
        budget=1000,
    )

    assert painted(wide).getchannel("A").getbbox() != painted(narrow).getchannel("A").getbbox()
