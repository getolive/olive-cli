# olive/context/extractors/markdown.py
from __future__ import annotations
import re
from pathlib import Path
from typing import List

from olive.context.extractors import BaseExtractor, register_extractor
from olive.context.extractors._common import make_entry, _rel_path
from olive.context.models import ASTEntry

@register_extractor((".md", ".markdown"))
class MarkdownExtractor(BaseExtractor):
    """Pull H1-H6 headings (or a short preview if none found)."""

    _HDR_RE = re.compile(r"^\s*(#{1,6})\s+(.*)")  # ◄ FIX #1

    def parse(self, path: Path) -> dict:
        src = path.read_text(errors="ignore")
        lines = src.splitlines()

        entries: List[ASTEntry] = []

        # ── collect headings ─────────────────────────────────────────
        for i, ln in enumerate(lines, 1):
            m = self._HDR_RE.match(ln)
            if m:
                level, title = len(m.group(1)), m.group(2).strip()
                entries.append(
                    make_entry(
                        name=title,
                        typ=f"heading_h{level}",
                        path=path,
                        start=i,
                        end=i,
                        code=ln,
                    )
                )

        # ── mandatory file-header (always first) ────────────────────
        header = make_entry(
            name=_rel_path(path),
            typ="file_header",
            path=path,
            start=1,
            end=len(lines),
            code="",
            meta={"lines": len(lines), "bytes": len(src)},
        )
        entries.insert(0, header)

        # ── FIX #2: fallback preview if no headings found ────────────
        if len(entries) == 1:
            for i, ln in enumerate(lines, 1):
                txt = ln.strip()
                if txt:
                    entries.append(
                        make_entry(
                            name=txt[:40] + ("…" if len(txt) > 40 else ""),
                            typ="md_preview",
                            path=path,
                            start=i,
                            end=i,
                            code=ln,
                        )
                    )
                    break

        return {
            "file": _rel_path(path),
            "summary": {
                "lines": len(lines),
                "total_definitions": len(entries),
                "imports": [],
                "lang": "markdown",
            },
            "entries": entries,
        }
