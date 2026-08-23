from collections.abc import Sequence
from functools import cache
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter

from undercover.media.blocks import Block
from undercover.media.layout import (
    CARD_FORMAT,
    CARD_HEIGHT,
    CARD_QUALITY,
    CARD_SIZE,
    FONT_BOLD,
    FONT_REGULAR,
    FOOTER_GAP,
    FOOTER_SPACE,
    GLOW_BLEED,
    GLOW_BLUR,
    GLOW_OPACITY,
    LAMP_CENTER,
    PROMO_INK,
    PROMO_SIZE,
    PROMO_TRACKING,
    RGB,
    SAFE_MARGIN,
    SHADOW_BLUR,
    SHADOW_COLOR,
    SHADOW_OFFSET,
    SHADOW_OPACITY,
    TEMPLATES_DIR,
    WORDMARK_INK,
    WORDMARK_SIZE,
    WORDMARK_TRACKING,
    Ink,
)
from undercover.media.typography import Face, draw_text, font
from undercover.texts import Cards


def render(background: str, glow: RGB, blocks: Sequence[Block], promo: str | None = None) -> bytes:
    content = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))

    band = content_height(promo)
    scale = squeeze(blocks, band)
    top = _stack_top(sum(block.space_before * scale + block.height for block in blocks), band)
    for block in blocks:
        top += block.space_before * scale
        block.draw(content, round(top))
        top += block.height
    _footer(content, promo)

    card = _background(background).copy()
    ink = content.getchannel("A")
    card.paste(
        Image.new("RGB", CARD_SIZE, SHADOW_COLOR),
        mask=_bleed(ink, SHADOW_BLUR, SHADOW_OFFSET, SHADOW_OPACITY),
    )
    card.paste(Image.new("RGB", CARD_SIZE, glow), mask=_bleed(ink, GLOW_BLUR, (0, 0), GLOW_OPACITY))
    card = Image.alpha_composite(card.convert("RGBA"), content).convert("RGB")

    buffer = BytesIO()
    card.save(buffer, format=CARD_FORMAT, quality=CARD_QUALITY, subsampling=0, optimize=True)
    return buffer.getvalue()


def squeeze(blocks: Sequence[Block], band: int) -> float:
    gaps = sum(block.space_before for block in blocks)
    solid = sum(block.height for block in blocks)
    if not gaps or solid + gaps <= band:
        return 1.0
    return max((band - solid) / gaps, 0.0)


def content_height(promo: str | None) -> int:
    return CARD_HEIGHT - 2 * (SAFE_MARGIN + GLOW_BLEED) - _footer_height(promo) - FOOTER_SPACE


@cache
def _background(file_name: str) -> Image.Image:
    with Image.open(TEMPLATES_DIR / file_name) as source:
        return source.convert("RGB")


def _stack_top(total: float, band: int) -> float:
    limit = SAFE_MARGIN + GLOW_BLEED
    if total > band:
        return (CARD_HEIGHT - total) / 2
    return min(max(LAMP_CENTER - total / 2, limit), limit + band - total)


def _bleed(alpha: Image.Image, blur: float, offset: tuple[int, int], opacity: float) -> Image.Image:
    spread = alpha.filter(ImageFilter.GaussianBlur(blur)).point(
        lambda level: round(level * opacity)
    )
    if offset == (0, 0):
        return spread

    shifted = Image.new("L", CARD_SIZE, 0)
    shifted.paste(spread, offset)
    return shifted


def _footer_lines(promo: str | None) -> tuple[tuple[str, Face, Ink, int], ...]:
    return (
        (Cards.SPY_PLATE, font(FONT_BOLD, WORDMARK_SIZE), WORDMARK_INK, WORDMARK_TRACKING),
        *(((promo, font(FONT_REGULAR, PROMO_SIZE), PROMO_INK, PROMO_TRACKING),) if promo else ()),
    )


def _footer_height(promo: str | None) -> int:
    lines = _footer_lines(promo)
    ink = sum(face.box(text, tracking).height for text, face, _, tracking in lines)
    return round(ink) + FOOTER_GAP * (len(lines) - 1)


def _footer(layer: Image.Image, promo: str | None) -> None:
    draw = ImageDraw.Draw(layer)
    lines = _footer_lines(promo)
    boxes = tuple(face.box(text, tracking) for text, face, _, tracking in lines)

    top: float = CARD_HEIGHT - SAFE_MARGIN - GLOW_BLEED - _footer_height(promo)
    for (text, face, ink, tracking), box in zip(lines, boxes, strict=True):
        position = (face.centered(text, tracking), top - box.top)
        draw_text(draw, position, text, face, ink, tracking)
        top += box.height + FOOTER_GAP
