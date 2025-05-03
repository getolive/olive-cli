"""
olive.context.rollups
─────────────────────
• Auto-discovers every .py file in this directory and imports it, so any
  new roll-up module you drop in is picked up automatically.

• Adds a universal *deduplication* filter that runs after any
  language-specific roll-up, collapsing repeated (type, name) pairs into
  “name ×N”.
"""

from __future__ import annotations

import pkgutil
from importlib import import_module
from collections import Counter
from typing import Iterable, List

from olive.context.extractors import ROLLUPS
from olive.context.models import ASTEntry

from olive.logger import get_logger

logger = get_logger(__name__)

# ────────────────────────────────────────────────────────────────────────
#  1. Dynamic discovery – import every sibling module
# ────────────────────────────────────────────────────────────────────────
for _mod in pkgutil.iter_modules(__path__):
    if _mod.name.startswith("_"):
        continue  # skip private helpers

    _str_mod = f"{__name__}.{_mod.name}"
    try:
        import_module(_str_mod)
        logger.info(f"imported {_str_mod}")
    except Exception as e:
        logger.error(f"failure to import {_str_mod}: {str(e)}")


# ────────────────────────────────────────────────────────────────────────
#  2. Universal dedupe roll-up – applied last for all suffixes
# ────────────────────────────────────────────────────────────────────────
def _dedupe(entries: List[ASTEntry], path: str) -> Iterable[ASTEntry]:
    seen: dict[tuple[str, str], ASTEntry] = {}
    counts: Counter = Counter()

    for e in entries:
        key = (e.type, e.name)
        counts[key] += 1
        if key not in seen:
            seen[key] = e

    for key, n in counts.items():
        if n > 1:
            base_name = seen[key].name.split(" ×", 1)[0]
            seen[key].name = f"{base_name} ×{n}"

    return seen.values()


# ----------------------------------------------------------------------
#  3. Outline-expander – splits a single *_outline entry into lines
# ----------------------------------------------------------------------
# def _expand_outline(entries: list[ASTEntry], path: str):
#    """If we have a single *_outline entry, split its code block into lines."""
#    if len(entries) == 1 and entries[0].type.endswith("_outline") and entries[0].code:
#        for i, ln in enumerate(entries[0].code.splitlines(), 1):
#            yield ASTEntry(
#                name=ln,  # keeps indentation
#                type=entries[0].type,  # e.g. html_outline
#                location=f"{path}:{i}",
#                summary="",
#                code="",
#                metadata={"outline_line": True},  # ★ generic flag
#            )
#    else:
#        yield from entries
#
def _expand_outline(entries: list[ASTEntry], path: str):
    """
    If a *_outline entry exists, explode its .code into one entry per line,
    but keep any file_header (or other) entries unchanged.
    """
    outline = next((e for e in entries if e.type.endswith("_outline")), None)
    if not outline or not outline.code:
        yield from entries  # nothing to do
        return

    # emit header(s) first, unchanged
    for e in entries:
        if e is outline:
            break
        yield e

    # split outline lines
    for i, ln in enumerate(outline.code.splitlines(), 1):
        yield ASTEntry(
            name=ln,  # preserves indentation
            type=outline.type,  # e.g. html_outline
            location=f"{path}:{i}",
            summary="",
            code=ln,  # keep the prototype text
            metadata={"outline": True, "start": i, "end": None},
        )

    # (in case there were entries after the outline – unlikely)
    for e in entries[entries.index(outline) + 1 :]:
        yield e


ROLLUPS["outline"] = _expand_outline


# register as catch-all (executes after any suffix-specific roll-up)
ROLLUPS["*"] = _dedupe
