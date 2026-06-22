from __future__ import annotations

import io
import logging
import sys

LOGGER_NAME = "api_aggregator"

logger = logging.getLogger(LOGGER_NAME)
if not logger.handlers:
    logger.addHandler(logging.NullHandler())


def get_logger(name: str | None = None) -> logging.Logger:
    if not name:
        return logger
    if name.startswith(LOGGER_NAME):
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


class _ColorFormatter(logging.Formatter):
    RESET = "\033[0m"
    COLORS = {
        logging.DEBUG: "\033[36m",  # Cyan
        logging.INFO: "\033[32m",  # Green
        logging.WARNING: "\033[33m",  # Yellow
        logging.ERROR: "\033[31m",  # Red
        logging.CRITICAL: "\033[35m",  # Magenta
    }

    def __init__(self, fmt: str, use_color: bool) -> None:
        super().__init__(fmt=fmt)
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        if not self.use_color:
            return message
        color = self.COLORS.get(record.levelno)
        if not color:
            return message
        return f"{color}{message}{self.RESET}"


def setup_default_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    for stream in (sys.stdout, sys.stderr):
        if not isinstance(stream, io.TextIOWrapper):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            # Fallback silently if stream doesn't allow reconfiguration.
            pass
    if root.handlers:
        return
    fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    stream = sys.stderr
    handler = logging.StreamHandler(stream)
    use_color = bool(getattr(handler.stream, "isatty", lambda: False)())
    handler.setFormatter(_ColorFormatter(fmt=fmt, use_color=use_color))
    root.setLevel(level)
    root.addHandler(handler)
