# cli/olive/sandbox/env.py

import os
import hashlib
import functools
import subprocess
from pathlib import Path
from rich import print
from olive.env import get_project_root
from olive.logger import get_logger
from olive.preferences import prefs

logger = get_logger(__name__)


def get_container_name() -> str:
    """
    Generate a stable container name based on the user and project path.
    """
    username = os.getenv("USER") or os.getenv("USERNAME") or "user"
    project_root = Path.cwd().resolve()
    project_hash = hashlib.sha1(str(project_root).encode()).hexdigest()[:8]
    return f"olive-sandbox-{username}-{project_hash}"


def get_mounts() -> list[tuple[str, str, bool]]:
    """
    Mount just the current Olive project into the container at /mnt/project.
    """
    project_root = get_project_root().resolve()
    return [(str(project_root), "/mnt/project", False)]


def docker_required(func):
    """First checks if sandbox mode enbaled, if so check Docker availability before executing a function or method."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # ✅ Skip check entirely if sandbox mode is disabled in prefs
        if not prefs.is_sandbox_enabled():
            return func(*args, **kwargs)

        try:
            subprocess.run(["docker", "info"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("[bold red]❌ Docker is not running or unavailable.[/bold red]")
            print("[dim]Please start Docker Desktop or the Docker daemon before using the Olive sandbox.[/dim]")
            logger.error("Docker daemon is not running or Docker not found.")
            return

        return func(*args, **kwargs)
    return wrapper

