# cli/olive/sandbox/env.py
"""
Shared helpers for Olive’s Docker sandbox layer.
"""

from __future__ import annotations

import functools
import hashlib
import os
import subprocess

from rich import print  # noqa: T201 – used for CLI error output

from olive import env
from olive.logger import get_logger
from olive.preferences import prefs

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Docker naming / mount helpers
# --------------------------------------------------------------------------- #
def get_container_name() -> str:
    """
    Deterministic container name:

        olive-sandbox-{user}-{project‑hash}[-{sid}]
    """
    username = os.getenv("USER") or os.getenv("USERNAME") or "user"
    project_hash = hashlib.sha1(str(env.get_project_root()).encode()).hexdigest()[:8]
    sid = env.get_session_id()  # single source
    return f"olive-sandbox-{username}-{project_hash}{'-' + sid if sid else ''}"


def get_mounts() -> list[tuple[str, str, bool]]:
    """
    Mount the *current* Olive project into the container at ``/mnt/project``.
    """
    proj = env.get_project_root().resolve()
    return [(str(proj), "/mnt/project", False)]


# --------------------------------------------------------------------------- #
# Decorator to gate Docker‑dependent ops
# --------------------------------------------------------------------------- #
def docker_required(func):
    """
    Skip the wrapped function entirely when the sandbox feature is disabled,
    otherwise ensure Docker is available and running.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not prefs.is_sandbox_enabled():  # feature off → run directly
            return func(*args, **kwargs)

        try:
            subprocess.run(["docker", "info"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("[bold red]❌ Docker is not running or unavailable.[/bold red]")
            print("[dim]Start Docker Desktop / dockerd to use the Olive sandbox.[/dim]")
            logger.error("Docker daemon is not running or Docker binary missing.")
            return

        return func(*args, **kwargs)

    return wrapper
