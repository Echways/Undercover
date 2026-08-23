from collections.abc import Sequence

from undercover.game.models import Winner
from undercover.media.blocks import Block, TextBlock, caption, footnote, headline, owner, stamp
from undercover.media.canvas import render
from undercover.media.layout import (
    BACKGROUND_NEUTRAL,
    BACKGROUND_UNDERCOVER,
    CARD_SUFFIX,
    FONT_BOLD,
    FONT_REGULAR,
    GLOW_COLD,
    GLOW_WARM,
    HINT_MAX_LINES,
    HINT_MAX_SIZE,
    HINT_MIN_SIZE,
    INK,
    INK_MUTED,
    INK_MUTED_WARM,
    RESULT_WORD_MAX_LINES,
)
from undercover.media.typography import fit
from undercover.texts import WIN_CAPTIONS, Cards

__all__ = [
    "CARD_SUFFIX",
    "render_ballot_card",
    "render_civilian_card",
    "render_hidden_card",
    "render_result_card",
    "render_speaker_card",
    "render_spy_card",
    "render_verdict_card",
]


def render_hidden_card(name: str) -> bytes:
    player = _clean(name, "имя игрока")
    return render(
        BACKGROUND_NEUTRAL,
        GLOW_COLD,
        (
            caption(Cards.HIDDEN_CAPTION, INK_MUTED),
            headline(player),
            footnote(Cards.HIDDEN_FOOTNOTE, INK_MUTED, space_before=56),
        ),
    )


def render_civilian_card(name: str, word: str) -> bytes:
    player = _clean(name, "имя игрока")
    secret = _clean(word, "слово")
    return render(
        BACKGROUND_NEUTRAL,
        GLOW_COLD,
        (
            owner(player, INK_MUTED),
            caption(Cards.CIVILIAN_CAPTION, INK_MUTED, space_before=48),
            headline(secret),
            footnote(Cards.CIVILIAN_FOOTNOTE, INK_MUTED, space_before=56),
        ),
    )


def render_spy_card(name: str, hint: str) -> bytes:
    player = _clean(name, "имя игрока")
    clue = _clean(hint, "подсказка")
    hint_font, hint_lines = fit(
        clue,
        FONT_REGULAR,
        max_size=HINT_MAX_SIZE,
        min_size=HINT_MIN_SIZE,
        max_lines=HINT_MAX_LINES,
    )
    return render(
        BACKGROUND_UNDERCOVER,
        GLOW_WARM,
        (
            owner(player, INK_MUTED_WARM),
            stamp(space_before=44),
            caption(Cards.SPY_CAPTION, INK_MUTED_WARM, space_before=56),
            TextBlock(
                lines=hint_lines,
                font=hint_font,
                color=INK,
                space_before=28,
                line_spacing=1.35,
            ),
            footnote(Cards.SPY_FOOTNOTE, INK_MUTED_WARM, space_before=56),
        ),
    )


def render_speaker_card(name: str) -> bytes:
    player = _clean(name, "имя игрока")
    return render(
        BACKGROUND_NEUTRAL,
        GLOW_COLD,
        (
            caption(Cards.SPEAKER_CAPTION, INK_MUTED),
            headline(player),
            footnote(Cards.SPEAKER_FOOTNOTE, INK_MUTED, space_before=56),
        ),
    )


def render_ballot_card() -> bytes:
    return render(
        BACKGROUND_NEUTRAL,
        GLOW_COLD,
        (
            caption(Cards.VOTE_CAPTION, INK_MUTED),
            headline(Cards.VOTE_HEADLINE),
            footnote(Cards.VOTE_FOOTNOTE, INK_MUTED, space_before=56),
        ),
    )


def render_verdict_card(name: str, is_spy: bool) -> bytes:
    player = _clean(name, "имя игрока")
    ink = INK_MUTED_WARM if is_spy else INK_MUTED
    return render(
        BACKGROUND_UNDERCOVER if is_spy else BACKGROUND_NEUTRAL,
        GLOW_WARM if is_spy else GLOW_COLD,
        (
            caption(Cards.VERDICT_CAPTION, ink),
            headline(player),
            caption(Cards.VERDICT_SPY if is_spy else Cards.VERDICT_CIVILIAN, ink, space_before=56),
        ),
    )


def render_result_card(spy_names: Sequence[str], word: str, winner: Winner | None = None) -> bytes:
    if not spy_names:
        raise ValueError("список шпионов не может быть пустым")

    spies = ", ".join(_clean(name, "имя шпиона") for name in spy_names)
    secret = _clean(word, "слово")
    word_font, word_lines = fit(
        secret,
        FONT_BOLD,
        max_size=HINT_MAX_SIZE,
        min_size=HINT_MIN_SIZE,
        max_lines=RESULT_WORD_MAX_LINES,
    )
    banner: Block = stamp() if winner is None else caption(WIN_CAPTIONS[winner], INK_MUTED_WARM)
    return render(
        BACKGROUND_UNDERCOVER,
        GLOW_WARM,
        (
            banner,
            caption(
                Cards.RESULT_SPIES_CAPTION if len(spy_names) > 1 else Cards.RESULT_SPY_CAPTION,
                INK_MUTED_WARM,
                space_before=56,
            ),
            headline(spies),
            caption(Cards.RESULT_WORD_CAPTION, INK_MUTED_WARM, space_before=48),
            TextBlock(
                lines=word_lines,
                font=word_font,
                color=INK,
                space_before=28,
                line_spacing=1.35,
            ),
        ),
    )


def _clean(value: str, field: str) -> str:
    text = " ".join(value.split())
    if not text:
        raise ValueError(f"{field} не может быть пустым")
    return text
