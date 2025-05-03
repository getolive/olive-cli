# olive/context/extractors/html.py
from __future__ import annotations
import re
from pathlib import Path
from typing import Optional, List
from olive.context.extractors import BaseExtractor, register_extractor
from olive.context.extractors.parser_cache import get_parser
from olive.context.models import ASTEntry
from olive.context.extractors._common import make_entry, _rel_path
from olive.logger import get_logger

logger = get_logger(__name__)


def _text(node) -> str:  # 🔹 safe bytes→str
    """bytes-safe across TS 0.20 (method) / 0.21 (property)."""
    if node is None:
        return ""
    t = getattr(node, "text", None)
    if callable(t):  # 0.20
        t = t()
    return (t or b"").decode(errors="ignore")


# -----------------------------------------------------------------------
@register_extractor((".html", ".htm", ".hbs", ".jinja"))
class HTMLExtractor(BaseExtractor):
    MAX_DEPTH = 2
    MAX_ITEMS = 40
    _SKIP_TAGS = {"script", "style"}

    def parse(self, path: Path) -> dict:
        parser = get_parser(path.suffix)
        if not parser:
            from olive.context.extractors.heuristic import HeuristicExtractor

            return HeuristicExtractor().parse(path)

        src = path.read_bytes()
        lines = src.decode(errors="ignore").splitlines()
        root = parser.parse(src).root_node

        outline: List[str] = []
        entries: List[ASTEntry] = []

        def label(node) -> Optional[str]:
            """Return html-like selector for an <element> or None to skip."""
            if node.type != "element":
                return None

            # ── 1️⃣ tag name via grammar fields (works on 0.20 & 0.21) ─────────
            st = node.child_by_field_name("start_tag")
            name_node = node.child_by_field_name("tag_name") or (
                st and st.child_by_field_name("tag_name")
            )
            tag_name = _text(name_node).strip().lower()

            # ── 2️⃣ regex fallback if grammar fields absent (edge cases) ───────
            if not tag_name:
                m = re.match(r"<\s*([a-zA-Z0-9:-]+)", _text(node))
                tag_name = m.group(1).lower() if m else ""

            if not tag_name or tag_name in self._SKIP_TAGS:
                return None

            # ── 3️⃣ build id/class suffix, if any ──────────────────────────────
            id_val = cls_val = None
            if st:
                for attr in (c for c in st.children if c.type == "attribute"):
                    k = _text(attr.child_by_field_name("name"))
                    v = _text(attr.child_by_field_name("value")).strip("\"' ")
                    if k == "id" and v:
                        id_val = v
                        break
                    if k == "class" and v and not cls_val:
                        cls_val = v.split()[0]

            if id_val:
                return f"{tag_name}#{id_val}"
            if cls_val:
                return f"{tag_name}.{cls_val}"

            # If we never determined a real tag, skip this node
            if tag_name == "element":
                return None

            extra = None
            if st:
                for attr in (c for c in st.children if c.type == "attribute"):
                    k = _text(attr.child_by_field_name("name"))
                    v = _text(attr.child_by_field_name("value")).strip('"\' ')
                    if k in {"aria-label", "role"} and v:
                        extra = f"~{v}"
                        break            # take the first meaningful one found

            if id_val:
                return f"{tag_name}#{id_val}"
            if cls_val:
                return f"{tag_name}.{cls_val}"
            if extra:
                return f"{tag_name}{extra}"
            return tag_name

        # ---------- DFS outline builder -------------------------------
        max_depth, cap = self.MAX_DEPTH, self.MAX_ITEMS

        def walk(node, depth=0):
            if node.type == "element" and depth <= max_depth:
                lbl = label(node)
                if lbl:
                    outline.append("  " * depth + lbl)
                    if len(outline) >= cap:
                        return
                if depth == max_depth:
                    return
            for ch in node.children:
                walk(ch, depth + 1)

        walk(root)

        if not outline:
            outline = ["html_file"]

        # 1️⃣ file-header entry --------------------------------------------------
        header = make_entry(  # ★
            name=_rel_path(path),
            typ="file_header",
            path=path,
            start=1,
            end=len(lines),
            code="",
            meta={"lines": len(lines), "bytes": len(src)},
        )
        entries.append(header)

        # 2️⃣ outline entry (one per file)  -------------------------------------
        outline_entry = make_entry(  # ★
            name=outline[0].strip(),
            typ="html_outline",
            path=path,
            start=1,
            end=len(lines),
            code="\n".join(outline),
            meta={"depth": self.MAX_DEPTH},
        )
        entries.append(outline_entry)

        return {
            "file": _rel_path(path),
            "summary": {
                "lines": len(lines),
                "bytes": len(src),
                "total_definitions": len(entries),
                "imports": [],
                "lang": "html",
            },
            "entries": entries,  # ★
        }
