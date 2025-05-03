# olive/context/trees.py
"""
olive.context.trees
───────────────────
Single-entry dispatcher that hands each file to the correct extractor.

Order of battle
---------------
1.  Look up extractor singleton by file-suffix in EXTRACTORS
2.  Fallback → HeuristicExtractor
3.  Guarantee a dict with at least {'entries': []} – never raises.
"""

from __future__ import annotations

from pathlib import Path

from olive.context.extractors import EXTRACTORS
from olive.context.extractors.heuristic import HeuristicExtractor
from olive.logger import get_logger

logger = get_logger(__name__)


# ----------------------------------------------------------------------
#  Public API
# ----------------------------------------------------------------------
def extract_ast_info(filepath: str) -> dict:
    """
    Robust wrapper – always returns a dict, never propagates exceptions.
    """
    path = Path(filepath)
    ext = path.suffix.lower()

    extractor = EXTRACTORS.get(ext, HeuristicExtractor())

    if isinstance(extractor, HeuristicExtractor) and ext in EXTRACTORS:
        # strict mode – if we expected a parser but it failed, better return {}
        logger.warning(f"{ext}: expected extractor failed, omitting file.")
        return {"file": str(path), "summary": {}, "entries": []}

    try:
        return extractor.parse(path)
    except Exception as e:  # pragma: no cover
        logger.warning(f"Extractor crash for {filepath}: {e!s} – using heuristic.")
        return HeuristicExtractor().parse(path)


# Opt-in re-export: callers that did “from …trees import extract_ast_info”
# will still work, but nothing else is leaked.
__all__ = ["extract_ast_info"]
