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
    CARD_WIDTH,
    CONTENT_HEIGHT,
    FONT_BOLD,
    FONT_REGULAR,
    FOOTER_GAP,
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
)
from undercover.media.typography import draw_tracked, font, text_width
from undercover.texts import Cards


def render(background: str, glow: RGB, blocks: Sequence[Block], promo: str | None = None) -> bytes:
    content = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))

    top = _stack_top(sum(block.space_before + block.height for block in blocks))
    for block in blocks:
        top += block.space_before
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


@cache
def _background(file_name: str) -> Image.Image:
    with Image.open(TEMPLATES_DIR / file_name) as source:
        return source.convert("RGB")


def _stack_top(total: int) -> float:
    limit = SAFE_MARGIN + GLOW_BLEED
    if total >= CONTENT_HEIGHT:
        return (CARD_HEIGHT - total) / 2
    return min(max(LAMP_CENTER - total / 2, limit), limit + CONTENT_HEIGHT - total)


def _bleed(alpha: Image.Image, blur: float, offset: tuple[int, int], opacity: float) -> Image.Image:
    spread = alpha.filter(ImageFilter.GaussianBlur(blur)).point(
        lambda level: round(level * opacity)
    )
    if offset == (0, 0):
        return spread

    shifted = Image.new("L", CARD_SIZE, 0)
    shifted.paste(spread, offset)
    return shifted


def _footer(layer: Image.Image, promo: str | None) -> None:
    draw = ImageDraw.Draw(layer)
    bottom = CARD_HEIGHT - SAFE_MARGIN - GLOW_BLEED
    lines = (
        (Cards.SPY_PLATE, font(FONT_BOLD, WORDMARK_SIZE), WORDMARK_INK, WORDMARK_TRACKING),
        *(((promo, font(FONT_REGULAR, PROMO_SIZE), PROMO_INK, PROMO_TRACKING),) if promo else ()),
    )
    height = sum(face.size for _, face, _, _ in lines) + FOOTER_GAP * (len(lines) - 1)

    top = bottom - height
    for text, face, ink, tracking in lines:
        width = text_width(face, text, tracking)
        draw_tracked(draw, ((CARD_WIDTH - width) / 2, top), text, face, ink, tracking)
        top += face.size + FOOTER_GAP
