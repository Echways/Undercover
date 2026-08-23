from collections.abc import Sequence

from undercover.game.models import Winner
from undercover.game.summary import GameSummary, Suspect
from undercover.media.blocks import Block, TextBlock, caption, footnote, stamp
from undercover.media.canvas import content_height, render
from undercover.media.layout import (
    BACKGROUND_NEUTRAL,
    BACKGROUND_UNDERCOVER,
    BANNER_SIZE,
    CASE_SIZE,
    FONT_BOLD,
    FONT_REGULAR,
    GLOW_COLD,
    GLOW_WARM,
    INK,
    INK_MUTED,
    INK_MUTED_WARM,
    METRICS_SIZE,
    ROSTER_OUT_INK,
    ROSTER_SPY_INK,
    SUMMARY_BANNER_SPACE,
    SUMMARY_HINT_MAX_LINES,
    SUMMARY_HINT_MAX_SIZE,
    SUMMARY_HINT_MIN_SIZE,
    SUMMARY_METRICS_SPACE,
    SUMMARY_SECTION_SPACE,
    SUMMARY_TIGHT_SPACE,
    SUMMARY_WORD_MAX_LINES,
    SUMMARY_WORD_MAX_SIZE,
    SUMMARY_WORD_MIN_SIZE,
    Ink,
)
from undercover.media.roster import RosterRow, roster
from undercover.media.typography import fit, plain
from undercover.texts import (
    CASE_DATE_FORMAT,
    PLAYERS,
    ROUNDS,
    RULESET_NAMES,
    WIN_CAPTIONS,
    Cards,
    duration_text,
    plural,
)

WORD_LINE_SPACING = 1.25
HINT_LINE_SPACING = 1.3


def render_summary_card(summary: GameSummary, promo: str | None = None) -> bytes:
    if not summary.suspects:
        raise ValueError("состав партии не может быть пустым")

    warm = summary.winner is not Winner.CIVILIANS
    head = _head(summary, warm)
    tail = _tail(summary, warm)
    budget = content_height(promo) - _extent(head) - _extent(tail) - SUMMARY_SECTION_SPACE

    return render(
        BACKGROUND_UNDERCOVER if warm else BACKGROUND_NEUTRAL,
        GLOW_WARM if warm else GLOW_COLD,
        (*head, roster(_rows(summary), budget, SUMMARY_SECTION_SPACE), *tail),
        promo,
    )


def _head(summary: GameSummary, warm: bool) -> tuple[Block, ...]:
    return (
        caption(_case(summary), _muted(warm), size=CASE_SIZE),
        _banner(summary),
        caption(Cards.SUMMARY_ROSTER, _muted(warm), space_before=SUMMARY_SECTION_SPACE),
    )


def _tail(summary: GameSummary, warm: bool) -> tuple[Block, ...]:
    hint = _hint(summary, warm)
    return (
        caption(Cards.RESULT_WORD_CAPTION, _muted(warm), space_before=SUMMARY_SECTION_SPACE),
        _word(summary),
        *((hint,) if hint is not None else ()),
        footnote(_metrics(summary), _muted(warm), SUMMARY_METRICS_SPACE, size=METRICS_SIZE),
    )


def _banner(summary: GameSummary) -> Block:
    if summary.winner is None:
        return stamp(space_before=SUMMARY_BANNER_SPACE)
    return caption(
        WIN_CAPTIONS[summary.winner], INK, space_before=SUMMARY_BANNER_SPACE, size=BANNER_SIZE
    )


def _case(summary: GameSummary) -> str:
    if summary.case_number is None:
        return Cards.SUMMARY_CASE_DATE.format(date=summary.opened_at.strftime(CASE_DATE_FORMAT))
    return Cards.SUMMARY_CASE.format(number=summary.case_number)


def _rows(summary: GameSummary) -> tuple[RosterRow, ...]:
    return tuple(_row(suspect) for suspect in summary.suspects)


def _row(suspect: Suspect) -> RosterRow:
    return RosterRow(
        name=plain(suspect.name, "имя игрока"),
        tag=_tag(suspect, Cards.SUMMARY_OUT_TAG),
        ink=ROSTER_OUT_INK if suspect.out_order is not None else INK,
        tag_ink=ROSTER_SPY_INK if suspect.is_spy else ROSTER_OUT_INK,
        short_tag=_tag(suspect, Cards.SUMMARY_OUT_TAG_SHORT),
    )


def _tag(suspect: Suspect, out_template: str) -> str:
    marks = []
    if suspect.is_spy:
        marks.append(Cards.SUMMARY_SPY_TAG)
    if suspect.out_order is not None:
        marks.append(out_template.format(order=suspect.out_order))
    return Cards.SUMMARY_TAG_JOINER.join(marks)


def _word(summary: GameSummary) -> TextBlock:
    face, lines = fit(
        plain(summary.word, "слово"),
        FONT_BOLD,
        max_size=SUMMARY_WORD_MAX_SIZE,
        min_size=SUMMARY_WORD_MIN_SIZE,
        max_lines=SUMMARY_WORD_MAX_LINES,
    )
    return TextBlock(
        lines=lines,
        face=face,
        color=INK,
        space_before=SUMMARY_TIGHT_SPACE,
        line_spacing=WORD_LINE_SPACING,
    )


def _hint(summary: GameSummary, warm: bool) -> TextBlock | None:
    if not summary.hints:
        return None

    template = Cards.SUMMARY_HINT_ONE if len(summary.hints) == 1 else Cards.SUMMARY_HINT_MANY
    hints = Cards.SUMMARY_HINT_JOINER.join(plain(hint, "подсказка") for hint in summary.hints)
    face, lines = fit(
        template.format(hints=hints),
        FONT_REGULAR,
        max_size=SUMMARY_HINT_MAX_SIZE,
        min_size=SUMMARY_HINT_MIN_SIZE,
        max_lines=SUMMARY_HINT_MAX_LINES,
    )
    return TextBlock(
        lines=lines,
        face=face,
        color=_muted(warm),
        space_before=SUMMARY_TIGHT_SPACE,
        line_spacing=HINT_LINE_SPACING,
    )


def _metrics(summary: GameSummary) -> str:
    parts = (
        f"{summary.rounds} {plural(summary.rounds, ROUNDS)}",
        f"{summary.players_count} {plural(summary.players_count, PLAYERS)}",
        duration_text(summary.duration),
        RULESET_NAMES[summary.ruleset],
    )
    return Cards.SUMMARY_METRICS_JOINER.join(parts)


def _muted(warm: bool) -> Ink:
    return INK_MUTED_WARM if warm else INK_MUTED


def _extent(blocks: Sequence[Block]) -> int:
    return sum(block.space_before + block.height for block in blocks)
