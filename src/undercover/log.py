import logging
import sys
from collections.abc import Sequence
from typing import Any, Final

import structlog
from structlog.stdlib import BoundLogger
from structlog.typing import Processor

DEFAULT_LEVEL: Final = "INFO"
PREVIEW_LIMIT: Final = 160

TIMESTAMPER: Processor = structlog.processors.TimeStamper(fmt="iso", utc=True)

SHARED_PROCESSORS: tuple[Processor, ...] = (
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    TIMESTAMPER,
    structlog.processors.StackInfoRenderer(),
)

structlog.configure(
    processors=[
        *SHARED_PROCESSORS,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=BoundLogger,
    cache_logger_on_first_use=True,
)


def configure_logging(level: str, *, json_output: bool | None = None) -> None:
    if json_output is None:
        json_output = not sys.stderr.isatty()

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=list(SHARED_PROCESSORS),
            processors=_render_chain(json_output),
        )
    )

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> BoundLogger:
    return structlog.stdlib.get_logger(name)


def bind(**fields: Any) -> None:
    structlog.contextvars.bind_contextvars(**fields)


def unbind_all() -> None:
    structlog.contextvars.clear_contextvars()


def preview(text: str | None, limit: int = PREVIEW_LIMIT) -> str | None:
    if text is None or len(text) <= limit:
        return text
    return f"{text[:limit]}…"


def _render_chain(json_output: bool) -> Sequence[Processor]:
    if json_output:
        return [
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ]
    return [
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        structlog.dev.ConsoleRenderer(colors=True),
    ]
