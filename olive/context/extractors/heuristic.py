from __future__ import annotations

import re
from pathlib import Path
from typing import List

from olive.context.extractors import register_extractor, BaseExtractor
from olive.context.models import ASTEntry
from olive.context.extractors._common import make_entry, _rel_path

# loose regexes
_FN_RE = re.compile(r"\b(function\s+|def\s+|async\s+def\s+)?([A-Za-z_]\w*)\s*\(")
_CLASS_RE = re.compile(r"\b(class|struct|enum)\s+([A-Za-z_]\w*)")
_STRING_OR_COMMENT = re.compile(r"""(['"]).*?\1|//.*?$|/\*.*?\*/""", re.S | re.M)


@register_extractor(tuple())  # *not* chosen by default, used as fallback
class HeuristicExtractor(BaseExtractor):
    """Last-ditch heuristic when no specific extractor is known."""

    def parse(self, path: Path) -> dict:
        lines = path.read_text(errors="ignore").splitlines()
        entries: List[ASTEntry] = []

        for i, ln in enumerate(lines, 1):
            clean = _STRING_OR_COMMENT.sub("", ln)
            for rx, typ in ((_FN_RE, "function"), (_CLASS_RE, "class")):
                m = rx.search(clean)
                if m:
                    entries.append(
                        make_entry(
                            name=m.group(2),
                            typ=typ,
                            path=_rel_path(path),
                            start=i,
                            end=i,
                            summary="",
                            code=ln.strip(),
                            meta={"heuristic": True},
                        )
                    )

        # file-header ------------------------------------------------ ★
        header = make_entry(
            name=path.name,
            typ="file_header",
            path=_rel_path(path),
            start=1,
            end=len(lines),
            code="",
            meta={"lines": len(lines), "bytes": len(path.read_bytes())},
        )
        entries.insert(0, header)

        return {
            "file": _rel_path(path),
            "summary": {
                "lines": len(lines),
                "total_definitions": len(entries),
                "imports": [],
                "lang": "plain",
            },
            "entries": entries,
        }
