"""Structured logging configuration using structlog.

In development (LOG_JSON=false): coloured human-readable output.
In production (LOG_JSON=true):   one JSON object per line, log rotation enabled.

Usage:
    from app.core.logging.setup import configure_logging
    configure_logging()
    import structlog
    logger = structlog.get_logger(__name__)
    logger.info("search_started", query=query, max_results=5)
"""
import logging
import logging.handlers
import sys
import os

try:
    import structlog
    HAS_STRUCTLOG = True
except ImportError:
    HAS_STRUCTLOG = False


def configure_logging(json_output: bool = False, log_dir: str = "logs") -> None:
    """Configure the root logger.

    Args:
        json_output: If True, emit JSON lines (production). Otherwise human-readable.
        log_dir: Directory for rotating log files. Pass '' to disable file logging.
    """
    level = logging.INFO

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    # Add rotating file handler when a log directory is specified
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=os.path.join(log_dir, "hybrid-search.log"),
            when="midnight",
            backupCount=7,
            encoding="utf-8",
        )
        handlers.append(file_handler)

    if HAS_STRUCTLOG and json_output:
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer(),
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        fmt = "%(message)s"
    elif HAS_STRUCTLOG:
        structlog.configure(
            processors=[
                structlog.stdlib.add_log_level,
                structlog.stdlib.add_logger_name,
                structlog.processors.TimeStamper(fmt="%H:%M:%S"),
                structlog.dev.ConsoleRenderer(),
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
        fmt = "%(message)s"
    else:
        fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

    for handler in handlers:
        handler.setFormatter(logging.Formatter(fmt))

    logging.basicConfig(level=level, handlers=handlers)


def get_logger(name: str):
    """Return a logger — structlog if available, stdlib otherwise."""
    if HAS_STRUCTLOG:
        import structlog
        return structlog.get_logger(name)
    return logging.getLogger(name)
