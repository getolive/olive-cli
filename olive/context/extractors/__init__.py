"""
olive.context.extractors
────────────────────────
Registry + base-types for language extractors and roll-up filters.

    •  BaseExtractor  – contract:   parse(Path) -> {"file", "summary", "entries"}
    •  EXTRACTORS     – maps file-suffix ("*.py") ➜ extractor singleton
    •  ROLLUPS        – maps file-suffix ("*.css") ➜ roll-up function
"""

from __future__ import annotations

import pkgutil

from importlib import import_module
from pathlib import Path
from typing import Protocol, Iterable, Callable, Dict, List

from olive.context.models import ASTEntry

from olive.logger import get_logger
logger = get_logger(__name__)


# ────────────────────────────────────────────────────────────────────────
#  Type contracts
# ────────────────────────────────────────────────────────────────────────
class BaseExtractor(Protocol):
    """
    Implement *one* of these per language family.

    parse(path) must return the canonical dict:
        {
            "file": str,
            "summary": {...},
            "entries": list[ASTEntry],
        }
    """

    def parse(self, path: Path) -> dict: ...


RollupFilter = Callable[[List[ASTEntry], str], Iterable[ASTEntry]]


# ────────────────────────────────────────────────────────────────────────
#  Global plug-in registries
# ────────────────────────────────────────────────────────────────────────
EXTRACTORS: Dict[str, BaseExtractor] = {}
ROLLUPS: Dict[str, RollupFilter] = {}


# ────────────────────────────────────────────────────────────────────────
#  Decorators
# ────────────────────────────────────────────────────────────────────────
def register_extractor(exts: tuple[str, ...]):
    """
    Attach a language extractor to one or more file suffixes.

    Example
    -------
        @register_extractor((".py",))
        class PythonExtractor:
            def parse(self, path): ...
    """

    def deco(cls: type[BaseExtractor]) -> type[BaseExtractor]:
        inst = cls()  # singleton keeps parser caches etc.
        for ext in exts:
            if ext in EXTRACTORS:  # pragma: no cover
                raise RuntimeError(f"Extractor already registered for {ext}")
            EXTRACTORS[ext] = inst
        return cls

    return deco


def register_rollup(exts: tuple[str, ...]):
    """
    Attach a post-extraction roll-up filter to one or more suffixes.

    A roll-up receives `(entries, path)` and yields a (possibly smaller)
    iterable of `ASTEntry` objects.
    """

    def deco(fn: RollupFilter) -> RollupFilter:
        for ext in exts:
            if ext in ROLLUPS:  # pragma: no cover
                raise RuntimeError(f"Roll-up already registered for {ext}")
            ROLLUPS[ext] = fn
        return fn

    return deco


# ----------------------------------------------------------------------
#  Auto-register built-in extractor plug-ins
# ----------------------------------------------------------------------
for mod in pkgutil.iter_modules(__path__):
    name = mod.name
    if name.startswith("_"):          # ignore _private.py, __pycache__, …
        continue
    try:
        _str_mod = f"{__name__}.{name}"
        import_module(_str_mod)
        logger.info(f"imported {_str_mod}")
    except Exception as e:
        logger.error(f"failure to import {_str_mod}: {str(e)}")
