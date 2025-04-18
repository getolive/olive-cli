# cli/olive/tools/src/__init__.py
from pathlib import Path
import subprocess
import tempfile
import re

from olive.logger import get_logger
from olive.context import context as olive_context
from olive.tools import ToolDescription
from olive.tools.toolkit import ToolResponse, validate_invocation, require_command
from olive.env import get_project_root

TOOL_NAME = "src"
logger = get_logger(f"tools.{TOOL_NAME}")


def describe_tool() -> ToolDescription:
    """
    Describe the 'src' tool, which enables read and write operations on source files
    within the current Olive context. It supports safe, local-first editing strategies
    such as replacing exact line ranges in well-known project files.

    🚨 Important Notes for the LLM:
    - Always verify that the file exists in the current Olive context (use `get` first).
    - Use `replace-lines` when you want to surgically update a file.
    - Avoid full file rewrites if you're replacing a small block.
    - All changes are made to real files but assumed to be under Git, so user can undo.
    """
    return {
        "name": TOOL_NAME,
        "description": (
            "Access and modify files inside the Olive context using safe, structured operations.\n\n"
            "Supported commands:\n"
            "- get: Returns the file contents with line numbers (for precise edits).\n"
            "- replace-lines: Replaces a known block in-place using start/end line numbers.\n"
            "- patch: Applies a Git-style unified diff (fallback, strict).\n"
            "Use `get` before editing to find anchors."
        ),
        "allowed_commands": ["get", "patch", "replace-lines", "create"],
        "examples": [
            '<olive_tool><tool>src</tool><input>{"command": "get", "path": "olive-cli/olive/llm.py"}</input></olive_tool>',
            '<olive_tool><tool>src</tool><input>{"command": "create", "path": "olive-cli/new_file.py", "content": "# New file\\nprint(\\"hello\\")"}</input></olive_tool>',
            '<olive_tool><tool>src</tool><input>{"command": "replace-lines", "path": "olive-cli/olive/shell.py", "start": 77, "end": 80, "lines": ["def reset():", "    print("done")"]}</input></olive_tool>',
            '<olive_tool><tool>src</tool><input>{"command": "patch", "path": "olive-cli/olive/shell.py", "patch": "--- a/olive-cli/olive/shell.py\\n+++ b/olive-cli/olive/shell.py\\n@@ -77,7 +77,11 @@\\n-    pass\\n+    print(\\"reset\\")", "dry_run": true}</input></olive_tool>',
        ],
    }


def run_tool(input: dict, invoked_tool_name: str = TOOL_NAME) -> dict:
    mismatch = validate_invocation(invoked_tool_name, TOOL_NAME)
    if mismatch:
        return mismatch.dict()

    missing = require_command(input)
    if missing:
        return missing.dict()

    command = input["command"].strip()
    path_str = input.get("path")

    if not path_str:
        return ToolResponse(
            success=False, reason="missing-path", error="Missing 'path' in input"
        ).dict()

    try:
        resolved_path = resolve_path(path_str, must_exist=(command != "create"))
    except ValueError as e:
        return ToolResponse(success=False, reason="path-error", error=str(e)).dict()

    try:
        if command == "get":
            logger.info(f"[src] Reading file: {resolved_path}")
            lines = resolved_path.read_text(encoding="utf-8").splitlines()
            numbered = [f"{i + 1}: {line}" for i, line in enumerate(lines)]
            return ToolResponse(
                success=True,
                stdout="\n".join(numbered),
                metadata={
                    "line_count": len(lines),
                    "path": str(resolved_path),
                },
            ).dict()

        elif command == "create":
            content = input.get("content")
            if not isinstance(content, str):
                return ToolResponse(
                    success=False,
                    reason="invalid-input",
                    error="'content' must be a string",
                ).dict()

            if resolved_path.exists():
                return ToolResponse(
                    success=False,
                    reason="file-exists",
                    error=(
                        f"File '{path_str}' already exists. "
                        "Use 'replace-lines' or 'patch' if you intend to modify it."
                    ),
                    metadata={"suggestions": ["replace-lines", "patch"]},
                ).dict()

            
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            resolved_path.write_text(content, encoding="utf-8")

            logger.info(f"[src] Created file: {resolved_path}")
            return ToolResponse(
                success=True,
                stdout=f"File '{path_str}' created successfully.",
                metadata={
                    "path": path_str,
                    "size_bytes": len(content.encode("utf-8")),
                },
            ).dict()

        elif command == "replace-lines":
            start = input.get("start")
            end = input.get("end")
            new_lines = input.get("lines")

            if (
                not isinstance(start, int)
                or not isinstance(end, int)
                or not isinstance(new_lines, list)
            ):
                return ToolResponse(
                    success=False,
                    reason="invalid-input",
                    error="'start', 'end' must be integers and 'lines' must be a list of strings",
                ).dict()

            logger.info(f"[src] Replacing lines {start}-{end} in {resolved_path}")
            original_lines = resolved_path.read_text(encoding="utf-8").splitlines()
            if start < 1 or start > end:
                return ToolResponse(
                    success=False,
                    reason="range-error",
                    error="Start line must be ≥ 1 and ≤ end line",
                ).dict()

            # Pad file with empty lines if 'end' goes beyond EOF
            padding_needed = max(0, end - len(original_lines))
            if padding_needed:
                original_lines += [""] * padding_needed

            new_content = original_lines[: start - 1] + new_lines + original_lines[end:]
            
            resolved_path.write_text("\n".join(new_content) + "\n", encoding="utf-8")
            return ToolResponse(
                success=True, stdout=f"Replaced lines {start}–{end} in {path_str}"
            ).dict()

        elif command == "patch":
            patch_data = input.get("patch")
            dry_run = input.get("dry_run", False)

            if not patch_data:
                return ToolResponse(
                    success=False,
                    reason="missing-patch",
                    error="Missing 'patch' content",
                ).dict()

            if not patch_data.strip().startswith("--- ") or "+++" not in patch_data:
                return ToolResponse(
                    success=False,
                    reason="malformed-patch",
                    error="Patch is missing '---' or '+++' headers",
                ).dict()

            if not has_valid_hunk_header(patch_data):
                return ToolResponse(
                    success=False,
                    reason="invalid-hunk-header",
                    error="Patch is missing valid hunk headers like '@@ -77,7 +77,11 @@'. Avoid '@@ def': unsupported by git.",
                ).dict()

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".patch", delete=False, encoding="utf-8"
            ) as patch_file:
                patch_file.write(patch_data)
                patch_file_path = patch_file.name

            logger.info("[src] Validating patch via git apply --check")
            dry_run_result = subprocess.run(
                ["git", "apply", "--check", patch_file_path],
                capture_output=True,
                text=True,
            )

            if dry_run_result.returncode != 0:
                stderr_output = dry_run_result.stderr.strip()
                logger.warning(f"[src] Patch rejected: {stderr_output}")
                return ToolResponse(
                    success=False, reason="patch-rejected", error=stderr_output
                ).dict()

            lines_changed = sum(
                1
                for line in patch_data.splitlines()
                if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
            )
            metadata = {
                "path": path_str,
                "lines_changed": lines_changed,
                "dry_run_output": dry_run_result.stdout.strip(),
            }

            if dry_run:
                return ToolResponse(
                    success=True,
                    stdout=dry_run_result.stdout.strip(),
                    metadata=metadata,
                ).dict()

            logger.info(f"[src] Applying patch for {path_str}")
            apply_result = subprocess.run(
                ["git", "apply", patch_file_path], capture_output=True, text=True
            )
            if apply_result.returncode != 0:
                logger.error(f"[src] Patch failed: {apply_result.stderr.strip()}")
                return ToolResponse(
                    success=False,
                    reason="patch-failed",
                    error=apply_result.stderr.strip(),
                ).dict()

            return ToolResponse(
                success=True,
                stdout=f"Patch applied to {path_str} (not committed)",
                metadata=metadata,
            ).dict()

        else:
            return ToolResponse(
                success=False,
                reason="unknown-command",
                error=f"Unknown command: {command}",
            ).dict()

    except Exception as e:
        logger.exception("[src] Exception during command execution")
        return ToolResponse(success=False, reason="exception", error=str(e)).dict()


def has_valid_hunk_header(patch: str) -> bool:
    """
    Check if a patch contains a valid Git hunk header.
    """
    return bool(re.search(r"^@@ -\d+(,\d+)? \+\d+(,\d+)? @@", patch, re.MULTILINE))


def resolve_path(path_str: str, must_exist=True) -> Path:
    """
    Ensure the provided file path is part of the hydrated Olive context.

    Args:
        path_str (str): A relative path to a file under the project root.
        must_exist (bool): If True, raises if the file does not exist. Use False for creation operations.

    Returns:
        Path: The fully resolved absolute path to the file on disk.

    Raises:
        ValueError: If the file is not in the context, doesn't exist, or is not a file.
    """
    base = get_project_root()
    if base is None:
        raise RuntimeError("Project root is not set. Cannot resolve paths.")

    requested_path = Path(path_str)
    context_files = {Path(f.path): f.path for f in olive_context.state.files}

    # Allow exact match if already relative and clean
    if must_exist and requested_path not in context_files:
        # Try to normalize: maybe user passed absolute path
        try:
            rel = requested_path.relative_to(base)
            if rel in context_files:
                requested_path = rel
            else:
                raise ValueError
        except Exception:
            raise ValueError(
                f"'{path_str}' is not a valid file in the current Olive context."
            )

    final_path = base / requested_path

    if must_exist and not final_path.exists():
        raise ValueError(f"File not found: {path_str}")
    if must_exist and not final_path.is_file():
        raise ValueError(f"Path is not a file: {path_str}")

    return final_path
