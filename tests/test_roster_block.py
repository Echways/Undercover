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
from undercover.media.roster import RosterBlock, RosterRow, roster
from undercover.media.typography import text_width

SPY_TAG = "ШПИОН · 1-Й ВЫЛЕТ"
SHORT_TAG = "ШПИОН · 1-Й"


def rows(count: int, name: str = "Аня", short_tag: str = "") -> tuple[RosterRow, ...]:
    return tuple(
        RosterRow(
            name=f"{name} {index}",
            tag=SPY_TAG,
            ink=INK,
            tag_ink=ROSTER_SPY_INK,
            short_tag=short_tag,
        )
        for index in range(count)
    )


def painted(block: RosterBlock) -> Image.Image:
    layer = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    block.draw(layer, 0)
    return layer


def test_a_short_roster_keeps_the_largest_size() -> None:
    assert roster(rows(4), budget=1000).name_font.size == ROSTER_MAX_SIZE


def test_a_roster_that_fits_stays_in_one_column() -> None:
    assert roster(rows(4), budget=1000).columns == 1


def test_a_crowded_roster_opens_a_second_column() -> None:
    block = roster(rows(16), budget=600)

    assert block.columns == 2
    assert block.height <= 600


def test_the_second_column_takes_the_tail_of_the_roster() -> None:
    block = roster(rows(15), budget=500)

    assert block.columns == 2
    assert block.rows_per_column == 8


def test_a_crowded_roster_shrinks_to_fit_the_budget() -> None:
    block = roster(rows(16), budget=400)

    assert block.height <= 400
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


def test_both_columns_stay_inside_the_content_column() -> None:
    block = roster(rows(16, name="Аполлинария-Иннокентия"), budget=500)

    box = painted(block).getchannel("A").getbbox()

    assert block.columns == 2
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


def test_a_split_roster_wears_the_short_tag() -> None:
    split = roster(rows(16, short_tag=SHORT_TAG), budget=500)

    assert split.columns == 2
    assert painted(split).tobytes() != painted(roster(rows(16), budget=500)).tobytes()


def test_one_column_keeps_the_full_tag() -> None:
    whole = roster(rows(4, short_tag=SHORT_TAG), budget=1000)

    assert whole.columns == 1
    assert painted(whole).tobytes() == painted(roster(rows(4), budget=1000)).tobytes()
