from undercover.media.blocks import TextBlock, caption, footnote, headline, owner, stamp
from undercover.media.canvas import render
from undercover.media.layout import (
    BACKGROUND_NEUTRAL,
    BACKGROUND_UNDERCOVER,
    CARD_SUFFIX,
    FONT_REGULAR,
    GLOW_COLD,
    GLOW_WARM,
    HINT_MAX_LINES,
    HINT_MAX_SIZE,
    HINT_MIN_SIZE,
    INK,
    INK_MUTED,
    INK_MUTED_WARM,
)
from undercover.media.typography import fit, plain
from undercover.texts import Cards

__all__ = [
    "CARD_SUFFIX",
    "render_ballot_card",
    "render_civilian_card",
    "render_hidden_card",
    "render_speaker_card",
    "render_spy_card",
    "render_verdict_card",
]


def render_hidden_card(name: str) -> bytes:
    player = plain(name, "имя игрока")
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
    player = plain(name, "имя игрока")
    secret = plain(word, "слово")
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
    player = plain(name, "имя игрока")
    clue = plain(hint, "подсказка")
    hint_face, hint_lines = fit(
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
                face=hint_face,
                color=INK,
                space_before=28,
                line_spacing=1.35,
            ),
            footnote(Cards.SPY_FOOTNOTE, INK_MUTED_WARM, space_before=56),
        ),
    )


def render_speaker_card(name: str) -> bytes:
    player = plain(name, "имя игрока")
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
    player = plain(name, "имя игрока")
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
