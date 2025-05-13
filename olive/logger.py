# cli/olive/logger.py
# cli/olive/logger.py
"""
olive.logger
============
Host  : <project>/.olive/logs/olive_session.log
Sandbox: <run_root>/…/logs/olive_session_<sid>.log
Rotates at 1 MB × 5 backups; hot-swaps on :reset.
"""

from __future__ import annotations

import logging
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict

from olive import env

# ─────────────────────────── internals
_LOCK = threading.RLock()
_LOGGERS: Dict[str, logging.Logger] = {}
_LOG_PATH: Path | None = None

_MAX_BYTES = 1_000_000
_BACKUP_COUNT = 5

# ─────────────────────────── helpers


def _initial_log_path() -> Path:
    """
    Cache the path **once**.  If OLIVE_SESSION_ID is unset we purposefully choose
    the unsuffixed host file and never change it later, even if a sandbox
    starts and sets a session-id.
    """
    logs_dir = env.get_current_logs_dir()
    sid = env.get_session_id()
    name = f"olive_session_{sid}.log" if sid else "olive_session.log"
    return logs_dir / name


def _log_path() -> Path:
    global _LOG_PATH
    if _LOG_PATH is None:
        _LOG_PATH = _initial_log_path()
    return _LOG_PATH


def _make_handler() -> RotatingFileHandler:
    h = RotatingFileHandler(
        _log_path(),
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
        delay=True,  # open on first emit
    )
    h.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    return h


def _prune_backups(path: Path) -> None:
    """Delete backups beyond BACKUP_COUNT so numbering stays contiguous."""
    backups = sorted(
        p for p in path.parent.glob(path.name + ".*") if p.suffix[1:].isdigit()
    )
    for old in backups[:-_BACKUP_COUNT]:
        old.unlink(missing_ok=True)


# ─────────────────────────── public API
def get_logger(name: str = "olive") -> logging.Logger:
    """Thread-safe, idempotent logger getter."""
    with _LOCK:
        if name in _LOGGERS:
            return _LOGGERS[name]

        lg = logging.getLogger(name)
        lg.setLevel(logging.DEBUG)
        lg.propagate = False
        if not lg.handlers:
            lg.addHandler(_make_handler())

        _LOGGERS[name] = lg
        return lg


def get_current_log_file() -> Path:
    return _log_path()


def force_log_rotation() -> bool:
    """
    Rotate and hot-swap handlers for *all* cached loggers.
    Returns True if at least one handler rolled.
    """
    rotated = False
    with _LOCK:
        _prune_backups(_log_path())

        for lg in _LOGGERS.values():
            for h in list(lg.handlers):
                if isinstance(h, RotatingFileHandler):
                    h.doRollover()
                    lg.removeHandler(h)
                    h.close()
                    lg.addHandler(_make_handler())
                    rotated = True
    return rotated
