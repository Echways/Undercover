import logging
import sys
from collections.abc import Sequence
from typing import Final

import structlog
from structlog.typing import Processor

DEFAULT_LEVEL: Final = "INFO"

TIMESTAMPER: Processor = structlog.processors.TimeStamper(fmt="iso", utc=True)

SHARED_PROCESSORS: tuple[Processor, ...] = (
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    TIMESTAMPER,
    structlog.processors.StackInfoRenderer(),
)


def configure_logging(level: str, *, json_output: bool | None = None) -> None:
    if json_output is None:
        json_output = not sys.stderr.isatty()

    structlog.configure(
        processors=[
            *SHARED_PROCESSORS,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

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
