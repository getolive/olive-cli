# cli/olive/logger.py
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

_LOGGERS = {}
_LOG_PATH = None

def init_logging():
    """Initialize the global logger and log path."""
    global _LOG_PATH
    from olive import env
    logs_dir = Path(".olive/logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    session_suffix = f"_{env.session_id}" if getattr(env, "session_id", None) else ""
    _LOG_PATH = logs_dir / f"olive_session{session_suffix}.log"

def get_logger(name="olive"):
    """Get or create a named logger instance."""
    if name in _LOGGERS:
        return _LOGGERS[name]

    if _LOG_PATH is None:
        init_logging()

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if not logger.handlers:
        handler = RotatingFileHandler(_LOG_PATH, maxBytes=1_000_000, backupCount=5)
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    _LOGGERS[name] = logger
    return logger

def get_session_log_path():
    return _LOG_PATH

def force_log_rotation(name="olive") -> bool:
    """
    Force a manual rotation of the log file used by Olive.
    Returns True if a rotation was triggered, else False.
    """
    logger = get_logger(name)
    logger.info(f"force_log_rotation({name}) has been called. proceeding.")
    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler):
            handler.doRollover()
            return True
    return False
