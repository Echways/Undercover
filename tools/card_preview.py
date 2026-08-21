import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from undercover.media.card_renderer import (
    render_civilian_card,
    render_hidden_card,
    render_result_card,
    render_speaker_card,
    render_spy_card,
)

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

DEFAULT_DESTINATION = Path("docs/preview")

logger = logging.getLogger("card_preview")


@dataclass(frozen=True, slots=True)
class Sample:
    file_name: str
    payload: bytes


def build_samples() -> tuple[Sample, ...]:
    return (
        Sample("hidden.png", render_hidden_card("Аня")),
        Sample("hidden_long_name.png", render_hidden_card("Владислав-Иннокентий")),
        Sample("civilian.png", render_civilian_card("Аня", "пицца")),
        Sample("civilian_long_word.png", render_civilian_card("Боря", "электрочайник")),
        Sample("civilian_phrase.png", render_civilian_card("Гера", "новогодняя ёлка")),
        Sample("spy_short_hint.png", render_spy_card("Аня", "его режут на куски")),
        Sample("speaker.png", render_speaker_card("Аня")),
        Sample("speaker_long_name.png", render_speaker_card("Владислав-Иннокентий")),
        Sample("result_one_spy.png", render_result_card(("Аня",), "пицца")),
        Sample(
            "result_many_spies.png",
            render_result_card(("Аня", "Владислав-Иннокентий", "Гера"), "новогодняя ёлка"),
        ),
        Sample(
            "spy_long_hint.png",
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
        (destination / sample.file_name).write_bytes(sample.payload)

    logger.info("Готово: %s", destination.resolve())


if __name__ == "__main__":
    main()
