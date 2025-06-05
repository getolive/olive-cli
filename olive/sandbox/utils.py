"""
olive.sandbox.utils
-------------------
Pure helpers shared by build- & life-cycle code.

Nothing in here touches Docker directly except `docker_required`.
"""

from __future__ import annotations

import functools
import hashlib
import importlib.util
import os
import subprocess
from pathlib import Path
from typing import Iterable

from rich import print as rprint  # noqa: T201 – CLI error output

from olive.logger import get_logger
from olive.preferences import prefs

logger = get_logger("sandbox")


# ─────────────────────────────  Olive source discovery  ──────────────────────────
def resolve_olive_mount_source() -> Path:
    """
    Return the filesystem *directory* that contains the Olive package.

    • Editable install / cloned repo → the repo root (has **pyproject.toml**)
    • Wheel / sdist install        → …/site-packages/olive
    """
    spec = importlib.util.find_spec("olive")
    if not spec:
        raise RuntimeError("Cannot locate installed Olive package.")

    if spec.origin is None and spec.submodule_search_locations:
        base = Path(list(spec.submodule_search_locations)[0])
    elif spec.origin:
        base = Path(spec.origin).parent
    else:  # pragma: no cover – should never happen
        raise RuntimeError("Invalid importlib spec for Olive.")

    # Walk one level up => repo root when running from editable install
    for cand in (base, base.parent):
        if (cand / "pyproject.toml").exists():
            return cand
    return base


# ─────────────────────────  Deterministic container naming  ─────────────────────
def get_container_name() -> str:
    from olive import env
    username = os.getenv("USER") or os.getenv("USERNAME") or "user"
    proj_hash = hashlib.sha1(str(env.get_project_root()).encode()).hexdigest()[:8]
    sid = env.get_session_id()
    return f"olive-sandbox-{username}-{proj_hash}-{sid}"
    #return f"olive-sandbox-{username}-{proj_hash}{'-' + sid if sid else ''}"


# ───────────────────────────────  Host → container mounts  ──────────────────────
def get_mounts() -> list[tuple[str, str, bool]]:
    """
    Always mount the active project root at **/mnt/project**.
    Other mounts are added later depending on prefs (`disk: mount`).
    """
    from olive import env
    proj = env.get_project_root().resolve()
    return [(str(proj), "/mnt/project", False)]


# ─────────────────────────────  Docker availability guard  ──────────────────────
def docker_required(fn):
    """
    Decorator – NOP when the sandbox feature is disabled.
    Otherwise ensures the Docker daemon is reachable.
    """

    @functools.wraps(fn)
    def _wrap(*args, **kw):
        if not prefs.is_sandbox_enabled():
            return fn(*args, **kw)

        try:
            subprocess.run(["docker", "info"], capture_output=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            rprint("[bold red]❌ Docker daemon not running.[/bold red]")
            return None
        return fn(*args, **kw)

    return _wrap


# ───────────────────────────────  Misc tiny helpers  ────────────────────────────
def flatten(it: Iterable[Iterable[str]]) -> list[str]:
    return [x for xs in it for x in xs]
