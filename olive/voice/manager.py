from olive.logger import get_logger
from olive.preferences import prefs
from .runtime import runtime

logger = get_logger(__name__)


def enable():
    prefs.set("voice", "enabled", value=True)
    runtime.ensure_ready()
    logger.info("Voice enabled")


def disable():
    prefs.set("voice", "enabled", value=False)
    runtime.shutdown()
    logger.info("Voice disabled")

