import logging
import sys
from typing import Literal

import structlog
from structlog.typing import Processor

LogLevel = Literal[
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    "CRITICAL",
]

LogFormat = Literal[
    "console",
    "json",
]


def configure_logging(
    *,
    log_level: LogLevel,
    log_format: LogFormat,
) -> None:
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(
            fmt="iso",
            utc=True,
        ),
    ]

    renderer: Processor

    if log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter_processors: list[Processor] = [
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
    ]

    if log_format == "json":
        formatter_processors.append(structlog.processors.format_exc_info)

    formatter_processors.append(renderer)

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=formatter_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    for logger_name in (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "sqlalchemy",
        "celery",
        "celery.task",
    ):
        external_logger = logging.getLogger(logger_name)
        external_logger.handlers.clear()
        external_logger.propagate = True

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
