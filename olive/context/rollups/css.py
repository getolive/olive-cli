# olive/context/rollups/css.py
from __future__ import annotations

import re
from typing import Iterable, List
from olive.context.extractors import register_rollup
from olive.context.models import ASTEntry

# ───── constants ────────────────────────────────────────────────────
_LIMIT               = 40        # absolute max items we ever emit
_TW_UTIL_RE          = re.compile(r"^[\.\-]?[a-z-]+?(?:[-_]\d+|\\:|\\/[0-9.]+)?$")
_UTILITY_HEAVY_RATIO = 0.55      # >55 % of rules look like .m-2, .lg:hidden, …

# --------------------------------------------------------------------
@register_rollup((".css", ".scss", ".sass"))
def css_rollup(entries: List[ASTEntry], path: str) -> Iterable[ASTEntry]:
    """
    Pare a stylesheet down to ≤40 signal-rich lines.

    1.  Always keep all @-rules and any selector that *doesn't* look like a
        tiny utility (e.g. `body`, `.btn-primary`, `#app`).
    2.  If the file is dominated by utility selectors (>55 %), keep only one
        of each base utility, and summarise the rest.
    3.  Finally, if we're still above the hard cap, truncate and say how many
        more selectors were omitted.
    """
    keep:   list[ASTEntry]             = []
    bucket: dict[str, list[ASTEntry]]  = {}   # base → all occurrences
    total_rules                        = len(entries)

    # ── 1. split into "keep immediately" vs. "utility candidates" ─────
    for e in entries:
        if e.type.startswith("@") or not e.name.lstrip().startswith("."):
            keep.append(e)
            continue

        base = _TW_UTIL_RE.sub("", e.name.split("{", 1)[0].strip())
        bucket.setdefault(base, []).append(e)

    util_rules = sum(len(v) for v in bucket.values())
    utility_heavy = util_rules / max(total_rules, 1) > _UTILITY_HEAVY_RATIO

    # ── 2. Tailwind-style collapse only if it's really a utility dump ──
    skipped_utils = 0
    if utility_heavy:
        for base, occurrences in bucket.items():
            keep.append(occurrences[0])        # keep the first occurrence
            skipped_utils += len(occurrences) - 1
    else:
        # not utility heavy → just keep all original non-@ selectors
        for occs in bucket.values():
            keep.extend(occs)

    if skipped_utils:
        keep.append(
            ASTEntry(
                name=f"Tailwind utilities (+{skipped_utils} more)",
                type="css_rollup",
                location=path,
                summary="collapsed near-duplicate utility rules",
                code="",
                metadata={},
            )
        )

    # ── 3. global hard cap – protect prompt size ----------------------
    if len(keep) > _LIMIT:
        excess = len(keep) - _LIMIT
        keep   = keep[:_LIMIT] + [
            ASTEntry(
                name=f"css_rollup (+{excess} more selectors)",
                type="css_rollup",
                location=path,
                summary="truncated long stylesheet",
                code="",
                metadata={},
            )
        ]

    return keep
