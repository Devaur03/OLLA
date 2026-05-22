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
import time

try:
    import structlog
    HAS_STRUCTLOG = True
except ImportError:
    HAS_STRUCTLOG = False


class SafeTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """
    A TimedRotatingFileHandler that never crashes the app on a failed rotation.

    On Windows, `uvicorn --reload` runs two processes (the reloader parent and
    the worker). Both open the same log file, so when one tries to roll the
    file over (rename it) Windows raises PermissionError [WinError 32] because
    the other process holds a handle. Stdlib's handler lets that exception
    propagate, spamming the console on every log record.

    This subclass swallows rotation errors: it keeps writing to the current
    file and advances the rollover timer so it does not retry on every record.
    """

    def doRollover(self) -> None:  # noqa: D102
        try:
            super().doRollover()
        except (OSError, PermissionError):
            # Another process holds the file. Skip this rotation gracefully.
            if self.stream is None:
                self.stream = self._open()
            # Advance rolloverAt past 'now' so we do not retry every record.
            now = int(time.time())
            new_rollover = self.computeRollover(now)
            while new_rollover <= now:
                new_rollover += self.interval
            self.rolloverAt = new_rollover


def configure_logging(json_output: bool = False, log_dir: str = "logs") -> None:
    """Configure the root logger.

    Args:
        json_output: If True, emit JSON lines (production). Otherwise human-readable.
        log_dir: Directory for rotating log files. Pass '' to disable file logging.
    """
    level = logging.INFO

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    # Add rotating file handler when a log directory is specified.
    # SafeTimedRotatingFileHandler tolerates the Windows `uvicorn --reload`
    # case where two processes share the log file; delay=True defers opening
    # the file until the first record, reducing handle contention.
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = SafeTimedRotatingFileHandler(
            filename=os.path.join(log_dir, "hybrid-search.log"),
            when="midnight",
            backupCount=7,
            encoding="utf-8",
            delay=True,
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
