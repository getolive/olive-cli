# cli/olive/context/utils.py

import subprocess
import ast
from pathlib import Path
from typing import List
from olive.preferences.admin import get_prefs_lazy
from .models import ASTEntry
from olive.logger import get_logger
from olive.context.injection import olive_context_injector
from olive.env import get_project_root

logger = get_logger(__name__)

@olive_context_injector(role="user")
def render_file_context_for_llm() -> List[str]:
    """
    Render user-facing prompt fragments from Olive context files.

    - If `abstract.mode.enabled: true`, inject structural summaries from AST metadata.
    - Otherwise, inject full file contents (respecting line limits).
    """
    from olive.context import context  # lazy import
    prefs = get_prefs_lazy()

    messages = []

    if prefs.is_abstract_mode_enabled():
        for path, entries in context.state.metadata.items():
            if not entries:
                continue
            summary = "\n".join(
                f"{entry.type} {entry.name} ({entry.location})"
                for entry in entries
            )
            messages.append(f"# metadata: {path} ({len(entries)} items)\n{summary}")

        logger.info(f"[context] Injected metadata for {len(context.state.metadata)} files.")
    else:
        for f in context.state.files:
            content = "\n".join(f.lines)
            messages.append(f"# file: {f.path} ({len(f.lines)} lines)\n{content}")
        logger.info(f"[context] Injected raw file content for {len(context.state.files)} files.")

    return messages


def get_git_diff_stats():
    try:
        result = subprocess.run(
            ["git", "diff", "--numstat"], capture_output=True, text=True, check=True
        )
        stats = {}
        for line in result.stdout.strip().splitlines():
            added, removed, path = line.split("\t")
            stats[path] = {"added": int(added), "removed": int(removed)}
        return stats
    except Exception:
        return {}


def is_abstract_mode_enabled() -> bool:
    prefs = get_prefs_lazy()

    return str(prefs.get("context", "abstract", "enabled", default=False)).lower() in (
        "1",
        "true",
        "yes",
    )


def extract_ast_info(filepath: str) -> dict:
    source = Path(filepath).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=filepath)
    lines = source.splitlines()

    entries: List[ASTEntry] = []
    imports = []

    def visit_node(node: ast.AST, parent: str = None):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            location = (
                f"{filepath}:{node.lineno}–{getattr(node, 'end_lineno', node.lineno)}"
            )
            summary = ast.get_docstring(node) or ""
            code = "\n".join(
                lines[node.lineno - 1 : getattr(node, "end_lineno", node.lineno)]
            )
            entries.append(
                ASTEntry(
                    name=node.name,
                    type="async_function"
                    if isinstance(node, ast.AsyncFunctionDef)
                    else "function",
                    location=location,
                    summary=summary,
                    code=code,
                    metadata={},
                )
            )
        elif isinstance(node, ast.ClassDef):
            location = (
                f"{filepath}:{node.lineno}–{getattr(node, 'end_lineno', node.lineno)}"
            )
            summary = ast.get_docstring(node) or ""
            code = "\n".join(
                lines[node.lineno - 1 : getattr(node, "end_lineno", node.lineno)]
            )
            entries.append(
                ASTEntry(
                    name=node.name,
                    type="class",
                    location=location,
                    summary=summary,
                    code=code,
                    metadata={},
                )
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(
                    f"import {alias.name}"
                    + (f" as {alias.asname}" if alias.asname else "")
                )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            level = "." * node.level
            names = ", ".join(alias.name for alias in node.names)
            imports.append(f"from {level}{module} import {names}")

        for child in ast.iter_child_nodes(node):
            visit_node(child, parent=node.name if hasattr(node, "name") else parent)

    visit_node(tree)

    return {
        "file": str(Path(filepath).resolve().relative_to(get_project_root())),
        "summary": {
            "lines": len(lines),
            "total_definitions": len(entries),
            "imports": imports,
        },
        "entries": entries,
    }
