# cli/olive/logger.py
"""
olive.logger
============

Small wrapper around `logging` that

• Writes to `<project>/.olive/logs/olive_session[_<sid>].log`
• Rotates at 1 MB × 5 files
• Keeps a *single* handler per‑logger instance
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict

from olive import env  # ← central paths / session‑id

_LOGGERS: Dict[str, logging.Logger] = {}
_LOG_FILE: Path | None = None


def _init_logging() -> None:
    """Create logs dir & figure out filename once per process."""
    global _LOG_FILE
    logs_dir = env.get_logs_root()  # ensures directory exists
    suffix = f"_{env.get_session_id()}" if env.get_session_id() else ""
    _LOG_FILE = logs_dir / f"olive_session{suffix}.log"


def get_logger(name: str = "olive") -> logging.Logger:
    """Cheap helper – always returns the same logger object per `name`."""
    if name in _LOGGERS:
        return _LOGGERS[name]

    if _LOG_FILE is None:
        _init_logging()

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if not logger.handlers:
        handler = RotatingFileHandler(_LOG_FILE, maxBytes=1_000_000, backupCount=5)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)

    _LOGGERS[name] = logger
    return logger


def get_current_log_file() -> Path | None:  # used by :logs command etc.
    return _LOG_FILE


def force_log_rotation(name: str = "olive") -> bool:
    """Manually rotate (useful in tests). Returns True if rotation occurred."""
    logger = get_logger(name)
    for h in logger.handlers:
        if isinstance(h, RotatingFileHandler):
            h.doRollover()
            return True
    return False
