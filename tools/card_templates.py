import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

from undercover.media.card_renderer import (
    BACKGROUND_NEUTRAL,
    BACKGROUND_UNDERCOVER,
    CARD_SIZE,
    TEMPLATES_DIR,
)

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

logger = logging.getLogger("card_templates")

RGB = tuple[int, int, int]

CARD_WIDTH, CARD_HEIGHT = CARD_SIZE

SOURCES_DIR = Path(__file__).resolve().parent.parent / "assets" / "backgrounds"

CONTRAST = 1.16
SATURATION = 1.08
EXPOSURE = 0.92

LAMP_CENTER_Y = 0.44
LAMP_RADIUS_X = 0.54
LAMP_RADIUS_Y = 0.38
LAMP_STRENGTH = 46

VIGNETTE_STRENGTH = 185
VIGNETTE_INSET_X = 0.16
VIGNETTE_INSET_Y = 0.10

GRAIN_AMOUNT = 5

CORNER_INSET = 58
CORNER_LENGTH = 68
CORNER_WIDTH = 2
CORNER_ALPHA = 44

PLATE_QUALITY = 95


@dataclass(frozen=True, slots=True)
class Plate:
    file_name: str
    source: str
    lamp: RGB


PLATES: tuple[Plate, ...] = (
    Plate(file_name=BACKGROUND_NEUTRAL, source="bg_blue.png", lamp=(96, 142, 214)),
    Plate(file_name=BACKGROUND_UNDERCOVER, source="bg_red.png", lamp=(206, 66, 72)),
)


def _fill(source: Path) -> Image.Image:
    with Image.open(source) as photo:
        image = photo.convert("RGB")

    scale = max(CARD_WIDTH / image.width, CARD_HEIGHT / image.height)
    scaled = image.resize(
        (round(image.width * scale), round(image.height * scale)),
        Image.Resampling.LANCZOS,
    )
    left = (scaled.width - CARD_WIDTH) // 2
    return scaled.crop((left, 0, left + CARD_WIDTH, CARD_HEIGHT))


def _grade(image: Image.Image) -> Image.Image:
    graded = ImageEnhance.Contrast(image).enhance(CONTRAST)
    graded = ImageEnhance.Color(graded).enhance(SATURATION)
    return ImageEnhance.Brightness(graded).enhance(EXPOSURE)


def _radial_mask(
    center: tuple[float, float], radius: tuple[float, float], strength: int, blur: float
) -> Image.Image:
    center_x, center_y = center
    radius_x, radius_y = radius

    mask = Image.new("L", CARD_SIZE, 0)
    ImageDraw.Draw(mask).ellipse(
        (center_x - radius_x, center_y - radius_y, center_x + radius_x, center_y + radius_y),
        fill=strength,
    )
    return mask.filter(ImageFilter.GaussianBlur(blur))


def _lamp(image: Image.Image, color: RGB) -> Image.Image:
    mask = _radial_mask(
        center=(CARD_WIDTH / 2, CARD_HEIGHT * LAMP_CENTER_Y),
        radius=(CARD_WIDTH * LAMP_RADIUS_X, CARD_HEIGHT * LAMP_RADIUS_Y),
        strength=LAMP_STRENGTH,
        blur=CARD_WIDTH * 0.34,
    )
    pool = Image.new("RGB", CARD_SIZE, (0, 0, 0))
    pool.paste(Image.new("RGB", CARD_SIZE, color), mask=mask)
    return ImageChops.screen(image, pool)


def _vignette(image: Image.Image) -> Image.Image:
    mask = ImageChops.invert(
        _radial_mask(
            center=(CARD_WIDTH / 2, CARD_HEIGHT / 2),
            radius=(CARD_WIDTH * (0.5 + VIGNETTE_INSET_X), CARD_HEIGHT * (0.5 + VIGNETTE_INSET_Y)),
            strength=255,
            blur=CARD_WIDTH * 0.16,
        )
    ).point(lambda level: round(level * VIGNETTE_STRENGTH / 255))

    darkened = image.copy()
    darkened.paste(Image.new("RGB", CARD_SIZE, (0, 0, 0)), mask=mask)
    return darkened


def _grain(image: Image.Image, seed: str) -> Image.Image:
    needed = CARD_WIDTH * CARD_HEIGHT
    stream = bytearray()
    block = seed.encode()
    while len(stream) < needed:
        block = hashlib.sha256(block).digest()
        stream += block

    noise = Image.frombytes("L", CARD_SIZE, bytes(stream[:needed]))
    noise = noise.point(lambda level: round(128 + (level - 128) * GRAIN_AMOUNT / 128))
    return ImageChops.add(image, noise.convert("RGB"), offset=-128)


def _corners(image: Image.Image) -> Image.Image:
    overlay = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    ink = (255, 255, 255, CORNER_ALPHA)

    left, top = CORNER_INSET, CORNER_INSET
    right, bottom = CARD_WIDTH - CORNER_INSET, CARD_HEIGHT - CORNER_INSET
    for x, y, step_x, step_y in (
        (left, top, CORNER_LENGTH, CORNER_LENGTH),
        (right, top, -CORNER_LENGTH, CORNER_LENGTH),
        (left, bottom, CORNER_LENGTH, -CORNER_LENGTH),
        (right, bottom, -CORNER_LENGTH, -CORNER_LENGTH),
    ):
        draw.line((x, y, x + step_x, y), fill=ink, width=CORNER_WIDTH)
        draw.line((x, y, x, y + step_y), fill=ink, width=CORNER_WIDTH)

    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def build_plate(plate: Plate) -> Image.Image:
    image = _fill(SOURCES_DIR / plate.source)
    image = _grade(image)
    image = _lamp(image, plate.lamp)
    image = _vignette(image)
    image = _grain(image, plate.file_name)
    return _corners(image)


def write_backgrounds(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for plate in PLATES:
        build_plate(plate).save(
            destination / plate.file_name,
            format="JPEG",
            quality=PLATE_QUALITY,
            subsampling=0,
            optimize=True,
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    write_backgrounds(TEMPLATES_DIR)
    logger.info("Фоны обновлены: %s", TEMPLATES_DIR)


if __name__ == "__main__":
    main()
