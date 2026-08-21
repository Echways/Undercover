import logging
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from undercover.media.card_renderer import (
    BACKGROUND_NEUTRAL,
    BACKGROUND_UNDERCOVER,
    CARD_SIZE,
    TEMPLATES_DIR,
)

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

logger = logging.getLogger("generate_card_templates")

RGB = tuple[int, int, int]

FRAME_INSET = 40

FRAME_RADIUS = 52
FRAME_WIDTH = 3
FRAME_ALPHA = 30

VIGNETTE_STRENGTH = 110


@dataclass(frozen=True, slots=True)
class Background:
    file_name: str
    top: RGB
    bottom: RGB
    glow: RGB


BACKGROUNDS: tuple[Background, ...] = (
    Background(
        file_name=BACKGROUND_NEUTRAL,
        top=(30, 41, 70),
        bottom=(11, 14, 26),
        glow=(86, 120, 205),
    ),
    Background(
        file_name=BACKGROUND_UNDERCOVER,
        top=(84, 20, 38),
        bottom=(22, 8, 14),
        glow=(214, 60, 78),
    ),
)


def _vertical_gradient(size: tuple[int, int], top: RGB, bottom: RGB) -> Image.Image:
    width, height = size
    column = Image.new("RGB", (1, height))
    for y in range(height):
        ratio = y / (height - 1)
        column.putpixel(
            (0, y),
            tuple(round(start + (end - start) * ratio) for start, end in zip(top, bottom)),
        )
    return column.resize(size, Image.Resampling.BICUBIC)


def _apply_glow(image: Image.Image, color: RGB) -> None:
    width, height = image.size
    radius = width * 0.5
    center_x, center_y = width / 2, height * 0.3

    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).ellipse(
        (center_x - radius, center_y - radius, center_x + radius, center_y + radius),
        fill=120,
    )
    image.paste(
        Image.new("RGB", image.size, color),
        mask=mask.filter(ImageFilter.GaussianBlur(radius * 0.5)),
    )


def _apply_vignette(image: Image.Image) -> None:
    width, height = image.size

    mask = Image.new("L", image.size, VIGNETTE_STRENGTH)
    ImageDraw.Draw(mask).ellipse(
        (-width * 0.18, -height * 0.12, width * 1.18, height * 1.12),
        fill=0,
    )
    image.paste(
        Image.new("RGB", image.size, (0, 0, 0)),
        mask=mask.filter(ImageFilter.GaussianBlur(width * 0.12)),
    )


def _apply_frame(image: Image.Image) -> Image.Image:
    width, height = image.size

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rounded_rectangle(
        (FRAME_INSET, FRAME_INSET, width - FRAME_INSET, height - FRAME_INSET),
        radius=FRAME_RADIUS,
        outline=(255, 255, 255, FRAME_ALPHA),
        width=FRAME_WIDTH,
    )
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def build_background(background: Background) -> Image.Image:
    image = _vertical_gradient(CARD_SIZE, background.top, background.bottom)
    _apply_glow(image, background.glow)
    _apply_vignette(image)
    return _apply_frame(image)


def write_backgrounds(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for background in BACKGROUNDS:
        build_background(background).save(destination / background.file_name, format="PNG")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    write_backgrounds(TEMPLATES_DIR)
    logger.info("Фоны обновлены: %s", TEMPLATES_DIR)


if __name__ == "__main__":
    main()
