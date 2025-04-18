# olive/shell/utils.py

import json
import tempfile
import subprocess
from shutil import which
from pathlib import Path
from enum import Enum, auto
from typing import Any, Dict, Optional
from olive.ui import console, print_error
from olive.logger import get_logger
from asyncio.subprocess import PIPE, create_subprocess_exec
from olive.preferences import prefs

logger = get_logger(__name__)


async def run_task_subprocess(spec_id: str) -> dict:
    """
    Launch `olive run-task <spec_id>` in Docker (if sandbox‐enabled)
    or on the host, but always capture & return the final JSON blob.
    """
    if prefs.is_sandbox_enabled():
        host_tasks = prefs.get("env", "project_root", default="") + "/.olive/run/tasks"
        container_tasks = "/workspace/.olive/run/tasks"
        cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{host_tasks}:{container_tasks}",
            "olive-sandbox:latest",
            "olive",
            "run-task",
            spec_id,
            "--json",
        ]
    else:
        cmd = ["olive", "run-task", spec_id, "--json"]

    proc = await create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
    out_b, err_b = await proc.communicate()

    if proc.returncode != 0:
        err = err_b.decode(errors="ignore").strip()
        raise RuntimeError(f"Task {spec_id} failed ({proc.returncode}): {err}")

    return json.loads(out_b.decode(errors="ignore"))


def get_pager() -> Optional[str]:
    """
    Return the first available pager command ('less' or 'more'),
    or None if neither is installed.
    """
    return which("less") or which("more")


def run_pager(path: Path) -> bool:
    """
    Open the given file path in a pager. Returns True if a pager was used,
    False otherwise.
    """
    pager = get_pager()
    if not pager:
        return False

    try:
        subprocess.run([pager, str(path)], check=True)
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to open {path} with {pager}: {e}")
    return True


def dump_json(data: Any, suffix: str = ".json", prefix: str = "olive_") -> Path:
    """
    Dump a Python object to a temporary JSON file and return its Path.
    """
    tmp = tempfile.NamedTemporaryFile(
        delete=False, suffix=suffix, prefix=prefix, mode="w", encoding="utf-8"
    )
    json.dump(data, tmp, indent=2)
    tmp.close()
    return Path(tmp.name)


def print_section(title: str, style: str = "highlight") -> None:
    """
    Print a section header surrounded by blank lines, using the given style.
    """
    console.print()
    console.print(f"[{style}]{title}[/{style}]")
    console.print()


def print_command_header(command: str) -> None:
    """
    Print the standard “Running command” header before executing a management command.
    """
    console.print()
    console.print(
        f"[primary]🛠️ Running command:[/primary] [secondary]{command}[/secondary]"
    )
    console.print()


# ────────────────────────────────────────────────────────────────────
# Helpers for pretty‑printing tool results
# ────────────────────────────────────────────────────────────────────


class ResultShape(Enum):
    """Define the shape of the result, helper for pretty-printing tool results"""

    PLAIN_TEXT = auto()
    TOOL_STD = auto()  # stdout / stderr / returncode keys
    GENERIC_DICT = auto()
    OTHER = auto()


def _analyse_result(obj: Any) -> ResultShape:
    """Determine ResultShape of obj, helper for pretty-printing tool results"""
    if isinstance(obj, str):
        return ResultShape.PLAIN_TEXT
    if isinstance(obj, Dict):
        keys = set(obj)
        if {"stdout", "stderr", "returncode"}.intersection(keys):
            return ResultShape.TOOL_STD
        return ResultShape.GENERIC_DICT
    return ResultShape.OTHER


def _render_tool_result(result: Any) -> None:
    """Pretty‑print a TaskResult payload or raw value."""
    from rich.pretty import Pretty
    from olive.tasks.models import TaskResult  # local import to avoid cycles

    # ── unwrap TaskResult → payload ──────────────────────────────────
    if isinstance(result, TaskResult):
        result = result.output

    # ── unwrap ToolResponse → stdout/stderr dict ─────────────────────
    # Shape: {'output': {...}, 'error': None, 'status': 'completed'}
    if (
        isinstance(result, dict)
        and {"output", "error", "status"} <= result.keys()
        and isinstance(result["output"], dict)
    ):
        result = result["output"]  # dive into the inner dict

    # ── dispatch on final shape ──────────────────────────────────────
    shape = _analyse_result(result)
    match shape:
        case ResultShape.PLAIN_TEXT:
            console.print(result)

        case ResultShape.TOOL_STD:
            if out := result.get("stdout", "").rstrip():
                console.print(out)
            if err := result.get("stderr", "").rstrip():
                print_error(err)
            if (rc := result.get("returncode")) is not None:
                console.print(f"[dim]exit code {rc}[/dim]")

        case ResultShape.GENERIC_DICT:
            console.print(Pretty(result, max_string=120))

        case ResultShape.OTHER:
            console.print(Pretty(result))
