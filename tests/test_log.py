import json
import logging
from collections.abc import Iterator

import pytest

from undercover.log import DEFAULT_LEVEL, configure_logging


@pytest.fixture(autouse=True)
def restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers = handlers
    root.setLevel(level)


def emit(
    capsys: pytest.CaptureFixture[str], *, level: str = DEFAULT_LEVEL, json_output: bool = True
) -> str:
    configure_logging(level, json_output=json_output)
    logging.getLogger("undercover.demo").info("собрана партия %s", "abc")
    return capsys.readouterr().err


def test_a_record_becomes_one_json_line(capsys: pytest.CaptureFixture[str]) -> None:
    record = json.loads(emit(capsys))

    assert record["event"] == "собрана партия abc"
    assert record["level"] == "info"
    assert record["logger"] == "undercover.demo"
    assert record["timestamp"].endswith("Z")


def test_russian_text_stays_readable(capsys: pytest.CaptureFixture[str]) -> None:
    assert "собрана партия abc" in emit(capsys)


def test_a_traceback_reaches_the_log(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(DEFAULT_LEVEL, json_output=True)
    try:
        raise ValueError("движок не завёлся")
    except ValueError:
        logging.getLogger("undercover.demo").exception("партия сорвалась")

    record = json.loads(capsys.readouterr().err)
    assert "Traceback (most recent call last)" in record["exception"]
    assert "ValueError: движок не завёлся" in record["exception"]


def test_locals_never_leak_into_the_log(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(DEFAULT_LEVEL, json_output=True)
    try:
        _secret = "424242:AA-token"
        raise ValueError("бум")
    except ValueError:
        logging.getLogger("undercover.demo").exception("упало")

    assert "424242:AA-token" not in capsys.readouterr().err


def test_the_console_format_is_not_json(capsys: pytest.CaptureFixture[str]) -> None:
    output = emit(capsys, json_output=False)

    assert "собрана партия abc" in output
    with pytest.raises(json.JSONDecodeError):
        json.loads(output)


def test_the_level_from_the_settings_wins(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("WARNING", json_output=True)
    logging.getLogger("undercover.demo").info("не должно попасть в вывод")

    assert capsys.readouterr().err == ""


def test_configuring_twice_does_not_double_the_lines(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(DEFAULT_LEVEL, json_output=True)
    configure_logging(DEFAULT_LEVEL, json_output=True)
    logging.getLogger("undercover.demo").info("одна строка")

    assert len(capsys.readouterr().err.strip().splitlines()) == 1


def test_third_party_loggers_get_the_same_format(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(DEFAULT_LEVEL, json_output=True)
    logging.getLogger("aiogram.dispatcher").warning("опрос прерван")

    record = json.loads(capsys.readouterr().err)
    assert record["logger"] == "aiogram.dispatcher"
    assert record["level"] == "warning"
