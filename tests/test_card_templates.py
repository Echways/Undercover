from pathlib import Path

from PIL import Image

import card_templates
from undercover.media.layout import (
    BACKGROUND_NEUTRAL,
    BACKGROUND_UNDERCOVER,
    CARD_SIZE,
    FONT_BOLD,
    FONT_REGULAR,
    TEMPLATES_DIR,
)


def test_assets_are_bundled_inside_the_package() -> None:
    for asset in (BACKGROUND_NEUTRAL, BACKGROUND_UNDERCOVER, FONT_REGULAR, FONT_BOLD):
        assert (TEMPLATES_DIR / asset).is_file(), asset


def test_source_photos_are_available_to_the_generator() -> None:
    for plate in card_templates.PLATES:
        assert (card_templates.SOURCES_DIR / plate.source).is_file(), plate.source


def test_backgrounds_have_the_card_geometry() -> None:
    for asset in (BACKGROUND_NEUTRAL, BACKGROUND_UNDERCOVER):
        with Image.open(TEMPLATES_DIR / asset) as background:
            assert background.size == CARD_SIZE, asset
            assert background.mode == "RGB", asset


def test_committed_backgrounds_match_their_generator(tmp_path: Path) -> None:
    card_templates.write_backgrounds(tmp_path)

    for asset in (BACKGROUND_NEUTRAL, BACKGROUND_UNDERCOVER):
        assert (tmp_path / asset).read_bytes() == (TEMPLATES_DIR / asset).read_bytes(), asset
