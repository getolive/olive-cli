from __future__ import annotations
from pathlib import Path
from typing import List

from olive.context.extractors import register_extractor, BaseExtractor
from olive.context.extractors.parser_cache import get_parser
from olive.context.extractors._common import make_entry, _rel_path
from olive.context.trees_static import interesting_nodes
from olive.logger import get_logger

logger = get_logger(__name__)


def _selector_text(node, src_lines) -> str:
    """
    Return the raw selector string for a `rule_set` node.
    (Everything up to the first ‘{’ on the start line.)
    """
    row = node.start_point[0]
    line = src_lines[row]
    return line.split("{", 1)[0].strip()


@register_extractor((".css", ".scss", ".sass"))
class CSSExtractor(BaseExtractor):
    """
    One ASTEntry per `rule_set` or `at_rule` at file depth 0.
    """

    def parse(self, path: Path) -> dict:
        parser = get_parser(path.suffix)
        if not parser:
            from olive.context.extractors.heuristic import HeuristicExtractor

            return HeuristicExtractor().parse(path)

        src = path.read_bytes()
        lines = src.decode(errors="ignore").splitlines()
        tree = parser.parse(src)
        root = tree.root_node

        ents: List = []
        ALLOWED = interesting_nodes("css")  # {rule_set, at_rule}

        # ── DFS depth-1 -------------------------------------------------
        for node in root.children:
            if node.type not in ALLOWED:
                continue

            s, e = node.start_point, node.end_point
            if node.type == "rule_set":  # .btn:hover { … }
                name = _selector_text(node, lines)
            else:  # at_rule  → keep first line
                name = lines[s[0]].strip()

            ents.append(
                make_entry(
                    name=name,
                    typ=node.type,  # rule_set | at_rule
                    path=path,
                    start=s[0] + 1,
                    end=e[0] + 1,
                    code="\n".join(lines[s[0] : e[0] + 1]),
                )
            )

        # file header (always first)
        header = make_entry(
            name=_rel_path(path),
            typ="file_header",
            path=path,
            start=1,
            end=len(lines),
            code="",
            meta={"lines": len(lines), "bytes": len(src)},
        )
        ents.insert(0, header)

        return {
            "file": _rel_path(path),
            "summary": {
                "lines": len(lines),
                "total_definitions": len(ents) - 1,  # minus header
                "imports": [],
                "lang": "css",
            },
            "entries": ents,
        }
