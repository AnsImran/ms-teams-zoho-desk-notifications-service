"""Centralized logging configuration for the Teams Notifications Service.

Provides structured JSON logging to rotating files and human-readable console
output.  Every module should use::

    from src.core.logger import get_logger
    logger = get_logger(__name__)

Environment variables
---------------------
LOG_LEVEL            : Root log level (default "INFO").
LOG_DIR              : Directory for rotating JSON log files (default "logs").
LOG_FILE_MAX_BYTES   : Max bytes per log file before rotation (default 10 MB).
LOG_FILE_BACKUP_COUNT: Number of rotated files to keep (default 5).
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler


# ---------------------------------------------------------------------------
# Custom JSON formatter (no external dependencies)
# ---------------------------------------------------------------------------

class JsonFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


# ---------------------------------------------------------------------------
# One-time setup (idempotent — safe to import from multiple modules)
# ---------------------------------------------------------------------------

_CONFIGURED = False


def setup_logging() -> None:
    """Configure the root logger with console and rotating-file handlers."""
    global _CONFIGURED  # noqa: PLW0603
    if _CONFIGURED:
        return
    _CONFIGURED = True

    # --- Read settings from environment ---
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        level = logging.INFO

    log_dir = os.getenv("LOG_DIR", "logs")
    max_bytes = int(os.getenv("LOG_FILE_MAX_BYTES", str(10 * 1024 * 1024)))
    backup_count = int(os.getenv("LOG_FILE_BACKUP_COUNT", "5"))

    # --- Root logger ---
    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers on reload / re-import
    if root.handlers:
        return

    # --- Console handler (human-readable) ---
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(console)

    # --- Rotating file handler (JSON structured) ---
    try:
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "service.log")
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(JsonFormatter())
        root.addHandler(file_handler)
    except OSError:
        # If file logging fails (read-only filesystem, etc.), continue with
        # console-only logging rather than crashing the service.
        root.warning("Could not set up file logging in '%s'; continuing with console only.", log_dir)

    # Quieten noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)


# Run setup on first import so every module that calls get_logger() inherits
# the configured handlers automatically.
setup_logging()


def get_logger(name: str) -> logging.Logger:
    """Return a named logger that inherits the shared configuration."""
    return logging.getLogger(name)
