import json
import logging
from collections.abc import Iterator

import pytest
from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError
from aiogram.methods import GetMe

from undercover import main as entrypoint
from undercover.config import ConfigurationError
from undercover.di import DependencyUnavailableError


@pytest.fixture(autouse=True)
def restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers = handlers
    root.setLevel(level)


def run_with(monkeypatch: pytest.MonkeyPatch, error: BaseException) -> None:
    async def _run() -> None:
        raise error

    monkeypatch.setattr(entrypoint, "_run", _run)
    entrypoint.main()


def fail_with(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    with pytest.raises(SystemExit) as exit_info:
        run_with(monkeypatch, error)
    assert exit_info.value.code == 1


def logged(capsys: pytest.CaptureFixture[str]) -> dict[str, str]:
    record: dict[str, str] = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    return record


def test_a_broken_environment_is_explained(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fail_with(monkeypatch, ConfigurationError("не задан BOT_TOKEN"))

    record = logged(capsys)
    assert record["event"] == "startup.failed"
    assert "не задан BOT_TOKEN" in record["reason"]


def test_an_unreachable_service_is_explained(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fail_with(monkeypatch, DependencyUnavailableError("нет подключения к Redis"))

    assert "нет подключения к Redis" in logged(capsys)["reason"]


def test_a_rejected_token_names_the_culprit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fail_with(monkeypatch, TelegramUnauthorizedError(method=GetMe(), message="Unauthorized"))

    record = logged(capsys)
    assert record["error"] == "TelegramUnauthorizedError"
    assert "BOT_TOKEN" in record["reason"]
    assert "@BotFather" in record["reason"]


def test_a_network_outage_is_explained(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fail_with(monkeypatch, TelegramNetworkError(method=GetMe(), message="таймаут"))

    assert "нет связи с Telegram" in logged(capsys)["reason"]


def test_a_failed_startup_leaves_no_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fail_with(monkeypatch, TelegramUnauthorizedError(method=GetMe(), message="Unauthorized"))

    assert "exception" not in logged(capsys)


def test_an_unexpected_failure_is_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    boom = RuntimeError("сломалось что-то новое")

    with pytest.raises(RuntimeError) as failure:
        run_with(monkeypatch, boom)

    assert failure.value is boom


def test_a_manual_stop_is_not_a_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run_with(monkeypatch, KeyboardInterrupt())

    record = logged(capsys)
    assert record["level"] == "info"
    assert record["event"] == "shutdown.by_hand"
