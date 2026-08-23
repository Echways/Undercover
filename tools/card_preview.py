import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from undercover.game.models import Ruleset, Winner
from undercover.game.summary import GameSummary, Suspect
from undercover.media.card_renderer import (
    CARD_SUFFIX,
    render_ballot_card,
    render_civilian_card,
    render_hidden_card,
    render_speaker_card,
    render_spy_card,
    render_verdict_card,
)
from undercover.media.summary_card import render_summary_card

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

DEFAULT_DESTINATION = Path("docs/preview")

PROMO = "t.me/undercover_bot"

TABLE: tuple[Suspect, ...] = (
    Suspect(name="Аня", is_spy=False, out_order=None),
    Suspect(name="Борис", is_spy=True, out_order=2),
    Suspect(name="Вера", is_spy=False, out_order=1),
    Suspect(name="Галя", is_spy=False, out_order=None),
)

logger = logging.getLogger("card_preview")


@dataclass(frozen=True, slots=True)
class Sample:
    name: str
    payload: bytes


def case(
    *,
    case_number: int | None = 17,
    winner: Winner | None = Winner.CIVILIANS,
    ruleset: Ruleset = Ruleset.CLASSIC,
    suspects: tuple[Suspect, ...] = TABLE,
    word: str = "пицца",
    hints: tuple[str, ...] = ("её режут на куски",),
    rounds: int = 3,
    duration: timedelta = timedelta(minutes=6),
) -> GameSummary:
    return GameSummary(
        case_number=case_number,
        opened_at=datetime(2026, 8, 23, 20, 0, tzinfo=UTC),
        winner=winner,
        ruleset=ruleset,
        suspects=suspects,
        word=word,
        hints=hints,
        rounds=rounds,
        duration=duration,
    )


def build_samples() -> tuple[Sample, ...]:
    return (
        Sample("hidden", render_hidden_card("Аня")),
        Sample("hidden_long_name", render_hidden_card("Владислав-Иннокентий")),
        Sample("civilian", render_civilian_card("Аня", "пицца")),
        Sample("civilian_long_word", render_civilian_card("Боря", "электрочайник")),
        Sample("civilian_phrase", render_civilian_card("Гера", "новогодняя ёлка")),
        Sample("spy_short_hint", render_spy_card("Аня", "его режут на куски")),
        Sample("speaker", render_speaker_card("Аня")),
        Sample("speaker_long_name", render_speaker_card("Владислав-Иннокентий")),
        Sample("ballot", render_ballot_card()),
        Sample("verdict_spy", render_verdict_card("Аня", is_spy=True)),
        Sample("verdict_civilian", render_verdict_card("Владислав-Иннокентий", is_spy=False)),
        Sample("summary_civilians_win", render_summary_card(case(), PROMO)),
        Sample("summary_spies_win", render_summary_card(case(winner=Winner.SPIES), PROMO)),
        Sample("summary_early_reveal", render_summary_card(case(winner=None), PROMO)),
        Sample("summary_two_players", render_summary_card(case(suspects=TABLE[:2]), PROMO)),
        Sample(
            "summary_sudden_death",
            render_summary_card(
                case(winner=Winner.SPIES, ruleset=Ruleset.SUDDEN_DEATH, rounds=1), PROMO
            ),
        ),
        Sample(
            "summary_many_spies",
            render_summary_card(
                case(
                    suspects=tuple(
                        Suspect(
                            name=f"Игрок {index + 1}",
                            is_spy=index < 3,
                            out_order=index + 1 if index < 4 else None,
                        )
                        for index in range(16)
                    ),
                    word="новогодняя ёлка",
                    hints=("её наряжают", "она колючая", "её ставят раз в год"),
                    duration=timedelta(hours=1, minutes=12),
                    rounds=9,
                ),
                PROMO,
            ),
        ),
        Sample(
            "summary_long_names",
            render_summary_card(
                case(
                    suspects=tuple(
                        Suspect(
                            name=f"Владислав-Иннокентий {index}",
                            is_spy=index == 1,
                            out_order=index or None,
                        )
                        for index in range(6)
                    ),
                    case_number=None,
                ),
                PROMO,
            ),
        ),
        Sample(
            "spy_long_hint",
            render_spy_card(
                "Владислав-Иннокентий",
                "Это бывает горячим, его заказывают компанией и делят на всех, "
                "а спорят обычно про начинку",
            ),
        ),
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DESTINATION
    destination.mkdir(parents=True, exist_ok=True)

    for sample in build_samples():
        (destination / f"{sample.name}.{CARD_SUFFIX}").write_bytes(sample.payload)

    logger.info("Готово: %s", destination.resolve())


if __name__ == "__main__":
    main()
