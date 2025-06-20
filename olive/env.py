# olive/env.py
"""
olive.env
=========

Single source‑of‑truth for:

• Project‑root discovery & locking
• User‑level config root (~/.olive)
• Standard *project‑local* tree
      <project>/.olive
      <project>/.olive/run
      <project>/.olive/logs
• Session‑ID helpers (used only when a sandbox / daemon spins one up)
• Sandbox helpers that work identically on host & inside the container
• Resource‑file resolver that survives editable installs & namespace packages
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from threading import Lock
from typing import Optional, Iterator
from functools import lru_cache
from importlib import resources as ir, util as iutil
from importlib.resources.readers import MultiplexedPath
from contextlib import contextmanager


# ──────────────────────────────────────────────────────────────
# internal state
# ──────────────────────────────────────────────────────────────
_LOCK = Lock()
_PROJECT_ROOT: Path = Path.cwd().resolve()  # locked‑in once per process
_SESSION_ID: str | None = os.getenv("OLIVE_SESSION_ID")  # may stay None


# ──────────────────────────────────────────────────────────────
# project root helpers
# ──────────────────────────────────────────────────────────────
def set_project_root(path: Path) -> None:
    """Change the canonical project root *once* per process."""
    global _PROJECT_ROOT
    with _LOCK:
        new_root = path.resolve()
        if _PROJECT_ROOT != new_root:
            _PROJECT_ROOT = new_root
            # If we’re on the host (not inside a running sandbox) and the
            # sandbox-dir env-var points outside the *current* project root,
            # drop it to prevent stale paths on subsequent calls.
            custom = os.getenv("OLIVE_SANDBOX_DIR")
            if custom and not is_in_sandbox():
                try:
                    custom_path = Path(custom).resolve()
                    if _PROJECT_ROOT not in custom_path.parents:
                        os.environ.pop("OLIVE_SANDBOX_DIR", None)
                except (OSError, RuntimeError):
                    # Path resolution failed → safest option is to unset
                    os.environ.pop("OLIVE_SANDBOX_DIR", None)


def get_project_root() -> Path:  # hot‑path – keep ultra‑cheap
    return _PROJECT_ROOT


# ──────────────────────────────────────────────────────────────
# user‑level (~/.olive) helper
# ──────────────────────────────────────────────────────────────
def get_user_root() -> Path:
    """Return ~/.olive (caller decides whether to create)."""
    return Path("~/.olive").expanduser()


# ──────────────────────────────────────────────────────────────
# project‑local directory helpers
# ──────────────────────────────────────────────────────────────
def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_dot_olive() -> Path:
    """`<project>/.olive` – lazily created on first call."""
    return _ensure_dir(get_project_root() / ".olive")


def get_dot_olive_settings() -> Path:
    """`<project>/.olive` – lazily created on first call."""
    return _ensure_dir(get_dot_olive() / "settings")


def get_run_root() -> Path:
    """`<project>/.olive/run` – ephemeral runtime data (tasks, sbx, …)."""
    return _ensure_dir(get_dot_olive() / "run")


def get_logs_root() -> Path:
    """`<project>/.olive/logs` – persistent logs."""
    return _ensure_dir(get_dot_olive() / "logs")


def get_current_logs_dir() -> Path:
    """
    Host  → <project>/.olive/logs
    Inside sandbox → get_sandbox_logs_dir()
    """
    return get_sandbox_logs_dir() if os.getenv("OLIVE_SANDBOX_DIR") else get_logs_root()


# ──────────────────────────────────────────────────────────────
# session‑id helpers  (only daemons / sandbox call generate)
# ──────────────────────────────────────────────────────────────
def get_session_id() -> str | None:
    return _SESSION_ID


def generate_session_id() -> str:
    """
    Return the current session-id if present, otherwise create & export a fresh
    8-char hex id.  Called by SandboxManager.start() on the host **before**
    the container is launched.
    """
    global _SESSION_ID

    if _SESSION_ID:  # already generated in this process
        return _SESSION_ID

    _SESSION_ID = uuid.uuid4().hex[:8]
    os.environ["OLIVE_SESSION_ID"] = _SESSION_ID
    return _SESSION_ID


# ──────────────────────────────────────────────────────────────
# sandbox directory helpers
# ──────────────────────────────────────────────────────────────
def get_sandbox_root() -> Path:
    """
    Build‑time artefacts (Dockerfile, snapshot, …)

    Host            → `<project>/.olive/sandbox`
    Inside container → `$OLIVE_SANDBOX_DIR`
    """
    custom = os.getenv("OLIVE_SANDBOX_DIR")
    return (
        Path(custom).expanduser().resolve() if custom else get_dot_olive() / "sandbox"
    )


def get_sandbox_run_root() -> Path:
    """
    Session‑scoped runtime root (shared path used by host & container):

        `<project>/.olive/run/sbx/<session_id>`
    """
    sid = get_session_id()
    if not sid:
        raise RuntimeError("OLIVE_SESSION_ID is not set – not in sandbox context.")

    return _ensure_dir(get_run_root() / "sbx" / sid)


# ──────────────────────────────────────────────────────────────
# sandbox‑scoped convenience getters
# ──────────────────────────────────────────────────────────────
def get_sandbox_rpc_dir() -> Path:
    """Return `<run_root>/sbx/<sid>/rpc` (created on first call)."""
    return _ensure_dir(get_sandbox_run_root() / "rpc")


def get_sandbox_result_dir() -> Path:
    """Return `<run_root>/sbx/<sid>/result` (created on first call)."""
    return _ensure_dir(get_sandbox_run_root() / "result")


def get_sandbox_logs_dir() -> Path:
    """Return `<run_root>/sbx/<sid>/result/logs` (created on first call)."""
    return _ensure_dir(get_sandbox_result_dir() / "logs")


def get_task_file(result_id: str) -> Path:
    """Convenience: absolute path for a *task‑spec* JSON inside the RPC dir."""
    return get_sandbox_rpc_dir() / f"{result_id}.json"


# ──────────────────────────────────────────────────────────────
# task‑results helpers (work for host *and* container)
# ──────────────────────────────────────────────────────────────
def get_tasks_root() -> Path:
    """`<project>/.olive/run/tasks` – tool/LLM result JSONs."""
    return _ensure_dir(get_run_root() / "tasks")


def get_result_file(result_id: str) -> Path:
    """Absolute path of a result JSON in the tasks directory."""
    return get_tasks_root() / f"{result_id}.result.json"


# ──────────────────────────────────────────────────────────────
# misc helpers (unchanged behaviour)
# ──────────────────────────────────────────────────────────────
@lru_cache(maxsize=None)
def is_in_sandbox() -> bool:
    """
    True when code executes inside the Olive Docker sandbox, False on the host.

    We rely on an invariant environment variable set in the Docker image *and*
    injected by `docker run` so the flag survives copy-mode vs mount-mode,
    multi-stage builds, etc.
    """
    return os.getenv("IS_OLIVE_SANDBOX") == "1"


def is_git_dirty() -> bool:
    from olive.context.utils import get_git_diff_stats

    return bool(get_git_diff_stats())


@contextmanager
def get_resource_path(pkg: str, name: Optional[str] = None) -> Iterator[Path]:
    """
    Yield a real on-disk Path to *name* inside *pkg*.

    Handles:
      • regular wheels / zip-safe wheels
      • editable installs on Python 3.12 (work-around synthetic path bug)
      • namespace packages (PEP 420)
    """
    try:
        traversable = ir.files(pkg)               # ← original happy path
    except NotADirectoryError:
        # ───── editable-install workaround ─────
        spec = iutil.find_spec(pkg)
        if not spec or not spec.submodule_search_locations:
            raise                                   # not our case → re-raise

        real_dirs = [p for p in spec.submodule_search_locations if Path(p).is_dir()]
        if not real_dirs:
            raise                                   # no real dirs → nothing we can do

        traversable = MultiplexedPath(*real_dirs)   # straddles all valid portions

    if name:
        traversable = traversable / name

    with ir.as_file(traversable) as path:            # still zip-safe
        yield path
