# olive/shell/utils.py

from __future__ import annotations

import json
import signal
import subprocess
import tempfile
from asyncio.subprocess import PIPE, create_subprocess_exec
from enum import Enum, auto
from pathlib import Path
from shutil import which
from typing import Any, Callable, Dict, Optional
import asyncio
import os
import sys
import functools
import inspect

from olive.logger import get_logger
from olive.preferences import prefs
from olive.ui import console, print_error
from olive.ui.spinner import safe_status as _maybe_spinner

logger = get_logger(__name__)


def cancellable(
    *,
    spinner: str = "dots",
    message: str = "[bold cyan]Working…[/bold cyan]",
    on_cancel: Callable[..., None] | None = None,
    run_in_executor: bool | None = None,  # auto-detect by default
):
    """
    Wrap an async *or* sync function so that:
      • A Rich spinner is shown while it runs.
      • Raw Ctrl-C (0x03) during the spinner *cancels immediately*.
      • Optional `on_cancel()` callback fires (sync or async).
    """

    def decorator(fn):
        async def _run(*args, **kwargs):
            loop = asyncio.get_running_loop()

            # ---- 1. decide whether the wrapped fn is blocking or coroutine
            is_coro = inspect.iscoroutinefunction(fn)
            run_in_exec = (
                bool(run_in_executor) if run_in_executor is not None else not is_coro
            )

            if run_in_exec:
                call = functools.partial(fn, *args, **kwargs)
                task = loop.run_in_executor(None, call)
            else:
                task = asyncio.create_task(fn(*args, **kwargs))

            # ---- 2. listen for raw ^C while prompt toolkit is suspended
            ctrlc = asyncio.Event()

            def _on_sigint(signum, frame):
                ctrlc.set()

            def _on_stdin():
                try:
                    if os.read(sys.stdin.fileno(), 1) == b"\x03":
                        ctrlc.set()
                except BlockingIOError:
                    pass  # incomplete byte

            loop.add_reader(sys.stdin.fileno(), _on_stdin)
            prev = signal.getsignal(signal.SIGINT)
            signal.signal(signal.SIGINT, _on_sigint)

            try:
                with _maybe_spinner(message=message, spinner=spinner):
                    ctrlc_task = asyncio.create_task(ctrlc.wait())
                    try:
                        done, _ = await asyncio.wait(
                            {task, ctrlc_task},
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                    finally:
                        # be tidy: if Ctrl-C did *not* fire, cancel the `wait()` task
                        if not ctrlc_task.done():
                            ctrlc_task.cancel()

                    if ctrlc.is_set():
                        task.cancel()
                        if on_cancel:
                            if inspect.iscoroutinefunction(on_cancel):
                                await on_cancel()
                            else:
                                on_cancel()
                        raise asyncio.CancelledError

                    return await task  # task finished normally
            finally:
                loop.remove_reader(sys.stdin.fileno())
                signal.signal(signal.SIGINT, prev)

        functools.update_wrapper(_run, fn)
        return _run

    return decorator


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
            out = str(result.get("stdout", "") or "")
            if out.rstrip():
                console.print(out.rstrip())
            err = str(result.get("stderr", "") or "")
            if err.rstrip():
                print_error(err.rstrip())
            if (rc := result.get("returncode")) is not None:
                if rc != 0:
                    console.print(f"[dim]exit code {rc}[/dim]")

        case ResultShape.GENERIC_DICT:
            console.print(Pretty(result, max_string=120))

        case ResultShape.OTHER:
            console.print(Pretty(result))
