# cli/olive/context/utils.py

import ast
import subprocess
from pathlib import Path
from typing import List

from olive.context.injection import olive_context_injector
from olive.env import get_project_root
from olive.logger import get_logger
from olive.preferences.admin import get_prefs_lazy

from .models import ASTEntry

logger = get_logger(__name__)


@olive_context_injector(role="user")
def render_file_context_for_llm() -> List:
    """
    Render user-facing prompt fragments from Olive context files.

    - If `abstract.mode.enabled: true`, inject structural summaries from AST metadata for main files.
    - Always append full file contents for extra_files at the end.
    """
    from olive.context import context  # lazy import

    prefs = get_prefs_lazy()

    messages = []

    # Collect main file context
    if prefs.is_abstract_mode_enabled():
        for path, entries in context.state.metadata.items():
            if not entries:
                continue
            summary = "\n".join(
                f"{entry.type} {entry.name} ({entry.location})" for entry in entries
            )
            messages.append(f"# metadata: {path} ({len(entries)} items)\n{summary}")

        logger.info(
            f" Injected metadata for {len(context.state.metadata)} files."
        )
    else:
        seen = set()
        for f in context.state.files:
            if f.path not in seen:
                seen.add(f.path)
                content = "\n".join(f.lines)
                messages.append(f"# file: {f.path} ({len(f.lines)} lines)\n{content}")
        logger.info(f" Injected raw file content for {len(seen)} files.")

    # Always append full content for extra_files (even in abstract mode)
    seen_extra = set()
    for ef in context.state.extra_files:
        if ef.path not in seen_extra:
            seen_extra.add(ef.path)
            content = "\n".join(ef.lines)
            messages.append(f"# file: {ef.path} ({len(ef.lines)} lines)\n{content}")

    print(f"{len(seen_extra)} extra seen.")
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
                    type=(
                        "async_function"
                        if isinstance(node, ast.AsyncFunctionDef)
                        else "function"
                    ),
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


def safe_add_extra_context_file(path_str, force=False):
    """
    Adds a file to Olive context by user-facing path (absolute or project-relative).
    Handles ignore rules, file reading, and error messaging.
    Returns True if added, False otherwise.
    """
    from olive.ui import print_error, print_success, print_warning
    from olive.context import context

    root = get_project_root()
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = (root / path).resolve()

    if not path.exists() or not path.is_file():
        print_error(f"{path} does not exist or is not a file.")
        return False

    try:
        rel_path = str(path.relative_to(root))
        path_for_context = rel_path
        outside_root = False
    except ValueError:
        # Path is outside project root
        path_for_context = str(path)
        outside_root = True

    excluded = context.is_file_excluded(path_for_context)
    if excluded and not force:
        print_error(
            f"{path_for_context} is excluded/ignored by your context rules. Use -f to force addition."
        )
        return False
    if excluded and force:
        print_warning(
            f"{path_for_context} is excluded by context rules, but forcibly adding (-f)."
        )
    if outside_root and not force:
        print_error(
            f"{path_for_context} is outside the project root. Use -f to force addition."
        )
        return False
    if outside_root and force:
        print_warning(
            f"{path_for_context} is outside the project root. Forcibly adding (-f)."
        )

    try:
        lines = path.read_text(errors="ignore").splitlines()
    except Exception as e:
        print_error(f"Failed to read {path_for_context}: {e}")
        return False
    try:
        context.add_extra_file(str(path_for_context), lines)
        context.save()
        print_success(f"Added {path_for_context} to context.")
        return True
    except FileExistsError:
        print_error(
            "Refused to add {str(path_for_context)} because this file is already in extra_files."
        )
    return False


def safe_remove_extra_context_file(path_str):
    """
    Removes a file from Olive context by user-facing path (absolute or project-relative).

    Handles appropriate path normalization and user-facing messages.
    Returns True if removed, False otherwise.
    """
    from olive.ui import print_error, print_success, print_info
    from olive.context import context

    root = get_project_root()
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = (root / path).resolve()

    try:
        rel_path = str(path.relative_to(root))
        path_for_context = rel_path
    except ValueError:
        # Path is outside project root
        path_for_context = str(path)

    try:
        count = context.remove_extra_file(str(path_for_context))
        context.save()
        if count == 0:
            print_info(f"{path_for_context} is not in extra context files.")
        else:
            print_success(f"Removed {path_for_context} from context.")
        return True

    except Exception as e:
        print_error(f"Failed to remove {path_for_context}: {e}")
    return False
