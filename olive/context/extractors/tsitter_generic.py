from __future__ import annotations

from pathlib import Path
from typing import List, Set

from olive.context.extractors import register_extractor, BaseExtractor
from olive.context.extractors.parser_cache import get_parser
from olive.context.trees_static import lang_from_ext, interesting_nodes
from olive.context.models import ASTEntry
from olive.context.extractors._common import make_entry
from olive.env import get_project_root
from olive.logger import get_logger

logger = get_logger(__name__)


# ── helpers ─────────────────────────────────────────────────────────────
def _rel_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(get_project_root()))
    except ValueError:
        return str(path)


def _identifier(node, lines) -> str | None:
    """Return the first child identifier-like token for a node."""
    for c in node.children:
        if c.type in {
            "identifier",
            "type_identifier",
            "property_identifier",
            "name",
            "tag_name",
        }:
            s, e = c.start_point, c.end_point
            return lines[s[0]][s[1] : e[1]].strip()
    return None


# ── generic extractor ──────────────────────────────────────────────────
@register_extractor(
    (
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".c",
        ".h",
        ".cc",
        ".cpp",
        ".rs",
        ".go",
        ".lua",
        ".lisp",
    )
)
class TSSitterExtractor(BaseExtractor):
    """
    Generic Tree-sitter extractor for most languages other than HTML & Python.
    """

    _DEPTH_LIMIT = {
        "javascript": 2,  # allow IIFE wrapper
        "typescript": 2,
        "go": 2,
    }  # ★ add more if needed

    def parse(self, path: Path) -> dict:
        ext = path.suffix
        lang = lang_from_ext(ext)  # ★ unified helper
        parser = get_parser(ext)
        if not parser:
            from olive.context.extractors.heuristic import HeuristicExtractor

            return HeuristicExtractor().parse(path)

        source = path.read_bytes()
        text = source.decode(errors="ignore").splitlines()
        root = parser.parse(source).root_node

        entries: List[ASTEntry] = []
        imports: List[str] = []

        # ── gather import statements ─────────────────────────────────────
        def _scan_imports(node):
            if node.type in {"import_statement", "import_declaration", "import_spec"}:
                s, e = node.start_point, node.end_point
                imports.append("\n".join(text[s[0] : e[0] + 1]).strip())
            for ch in node.children:
                _scan_imports(ch)

        _scan_imports(root)

        allowed: Set[str] = interesting_nodes(lang)
        max_depth = self._DEPTH_LIMIT.get(lang, 1)  # ★ depth per lang

        # ── DFS walker ───────────────────────────────────────────────────
        def walk(node, depth=0):
            if depth <= max_depth and node.type in allowed:
                s, e = node.start_point, node.end_point
                entries.append(  # ★
                    make_entry(
                        name=_identifier(node, text) or "<anon>",
                        typ=node.type,
                        path=path,
                        start=s[0] + 1,
                        end=e[0] + 1,
                        code="\n".join(text[s[0] : e[0] + 1]),
                    )
                )

            for ch in node.children:
                walk(ch, depth + 1)

        walk(root)

        # ── single file-header (prepend once) ───────────────────────── ★
        header = make_entry(
            name=_rel_path(path),  # visible in prompt
            typ="file_header",
            path=path,  # keep the real Path object
            start=1,
            end=len(text),
            code="",
            meta={"lines": len(text), "bytes": len(source)},
        )
        entries.insert(0, header)

        return {
            "file": _rel_path(path),
            "summary": {
                "lines": len(text),
                "total_definitions": len(entries),
                "imports": imports,
                "lang": lang,
            },
            "entries": entries,
        }
