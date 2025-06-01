"""
Olive Voice module
==================

Re-wired to use the high-throughput recogniser in stt.py.
Nothing heavy happens at import time – models spin up lazily when
`runtime.ensure_ready()` is first called.

Example
-------
    from olive.voice import runtime
    runtime.ensure_ready()
"""
from olive.logger import get_logger
from .runtime import runtime            # singleton
from .models import ensure_models

logger = get_logger(__name__)
logger.debug("olive.voice imported – stt runtime stub ready")

__all__ = ["runtime", "ensure_models"]

