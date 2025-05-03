from __future__ import annotations

import ast
from pathlib import Path
from typing import List

from olive.context.extractors import register_extractor, BaseExtractor
from olive.context.models import ASTEntry
from olive.context.extractors._common import make_entry, _rel_path 


# ── main extractor ──────────────────────────────────────────────────────
@register_extractor((".py",))
class PythonExtractor(BaseExtractor):
    """AST-based extractor for Python source files."""

    def parse(self, path: Path) -> dict:
        src = path.read_text(encoding="utf8", errors="ignore")
        lines = src.splitlines()
        tree = ast.parse(src, filename=str(path))

        entries: List[ASTEntry] = []
        imports: List[str] = []

        def visit(node: ast.AST):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                entries.append(
                    make_entry(
                        name=node.name,
                        typ="function",
                        start=node.lineno,
                        end=getattr(node, "end_lineno", node.lineno),
                        path=path,
                        summary=ast.get_docstring(node) or "",
                        code="\n".join(
                            lines[
                                node.lineno - 1 : getattr(
                                    node, "end_lineno", node.lineno
                                )
                            ]
                        ),
                    )
                )
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                base = (
                    "import "
                    if isinstance(node, ast.Import)
                    else f"from {'.' * node.level}{node.module or ''} import "
                )
                imports.append(
                    base
                    + ", ".join(
                        f"{a.name}{f' as {a.asname}' if a.asname else ''}"
                        for a in node.names
                    )
                )
            for child in ast.iter_child_nodes(node):
                visit(child)

        visit(tree)

        # ── file header (always first) ───────────────────────────── ★
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

        return {
            "file": _rel_path(path),
            "summary": {
                "lines": len(lines),
                "total_definitions": len(entries),
                "imports": imports,
                "lang": "python",
            },
            "entries": entries,
        }
