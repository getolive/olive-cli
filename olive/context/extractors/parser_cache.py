"""
olive.context.extractors.parser_cache
─────────────────────────────────────
LRU-cached factory for Tree-sitter Parser objects.

• Handles both 0.20 (single-arg) and 0.21 (two-arg) Language constructors.
• Emits only DEBUG logs on pointer-probe misses; no spurious ERROR noise.
"""

from __future__ import annotations

import ctypes
from functools import cache
from importlib import import_module
from typing import Optional

from tree_sitter import Parser, Language

from olive.context.trees_static import GRAMMARS
from olive.logger import get_logger

logger = get_logger(__name__)
#DEBUG = logger.isEnabledFor(10)  # DEBUG == 10 in std logging
DEBUG = True

# ── PyCapsule helpers ───────────────────────────────────────────────────
_PyCapsule_GetPointer = ctypes.pythonapi.PyCapsule_GetPointer
_PyCapsule_GetPointer.restype = ctypes.c_void_p
_PyCapsule_GetPointer.argtypes = [ctypes.py_object, ctypes.c_char_p]

_PyCapsule_GetName = ctypes.pythonapi.PyCapsule_GetName
_PyCapsule_GetName.restype = ctypes.c_char_p
_PyCapsule_GetName.argtypes = [ctypes.py_object]


def _addr_from_capsule(capsule) -> int | None:
    """Return TS_LANGUAGE* address or None (quietly)."""
    for hint in (None, b"", _PyCapsule_GetName(capsule)):
        try:
            ptr = _PyCapsule_GetPointer(capsule, hint)
            if ptr:
                return ptr
        except Exception as e:  # pragma: no cover
            if DEBUG:
                logger.debug(f"_addr_from_capsule miss: {e} ({str(capsule)})")
    return None


# ── public API ──────────────────────────────────────────────────────────
@cache
def get_parser(ext: str) -> Optional[Parser]:
    """
    Return a ready Parser for *ext* (e.g. '.js'), or None if the grammar
    wheel is unavailable or failed to load.  Result cached per extension.
    """
    pkg = GRAMMARS.get(ext)
    if not pkg:
        if DEBUG:
            logger.debug(f"parser_cache: unknown extension {ext!r}")
        return None

    # 1. import grammar wheel
    try:
        mod = import_module(pkg)
    except ModuleNotFoundError:
        logger.warning(f"No tree-sitter wheel for {ext}; falling back.")
        return None

    # 2. get capsule / language object from module
    capsule = (
        mod.language()
        if callable(getattr(mod, "language", None))
        else getattr(mod, "TREE_SITTER_LANGUAGE", None)
    )
    if capsule is None:
        logger.warning(f"{pkg} exposes no grammar pointer; falling back.")
        return None

    # 3. materialise Language object (old & new ABI)
    if isinstance(capsule, Language):
        lang = capsule
    else:
        # Fast path: old 0.20 single-arg ctor
        try:
            lang = Language(capsule)
        except Exception:
            # Slow path: new 0.21 two-arg ctor via pointer
            ptr = _addr_from_capsule(capsule)
            if not ptr:
                logger.warning(f"{pkg}: could not initialise Language from capsule.")
                return None
            lang = Language(ptr, pkg.rsplit("_", 1)[-1])

    # 4. instantiate Parser
    try:
        parser = Parser()
        parser.set_language(lang)
        if DEBUG:
            logger.debug(f"parser_cache: built parser for {ext} ({pkg})")
        return parser
    except Exception as e:  # pragma: no cover
        logger.warning(f"{pkg}: parser creation failed ({e}); falling back.")
        return None
