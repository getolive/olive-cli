# cli/olive/env.py
"""
Core Olive environment utilities.

This module handles:
- Git branch awareness
- User-level Olive config directory resolution
- Global project root resolution and locking (to ensure path consistency across tool calls and threads)
"""
import importlib.util
from pathlib import Path
from olive.logger import get_logger
from typing import Optional

logger = get_logger(__name__)

# 🧭 Locked-in root of the Olive project
_PROJECT_ROOT = Path.cwd().resolve()


def get_olive_base_path() -> Path:
    """
    Get the path to the .olive directory at the current project root.

    Returns:
        Path: .olive path, relative to the locked-in project root.
    """
    return get_project_root() / ".olive"


def get_olive_root() -> Path | None:
    """
    Resolve the path to the user's Olive configuration directory (~/.olive).

    Returns:
        Path | None: The expanded path if it exists, otherwise None.
    """
    path = Path("~/.olive/").expanduser()
    return path if path.exists() else None


def set_project_root(path: Path):
    """
    Lock in the root directory for project-relative file resolution.

    Args:
        path (Path): The root path to use for context hydration and file validation.
    """
    global _PROJECT_ROOT
    if _PROJECT_ROOT != path.resolve():
        _PROJECT_ROOT = path.resolve()
        _msg = f"OLIVE HAS CHANGED ITS ROOT PROJECT PATH TO: {_PROJECT_ROOT}"
        logger.info(_msg)
        from rich import print

        print(f"[bold cyan]{_msg}[/bold cyan]")


def get_project_root() -> Path:
    """
    Get the current locked-in project root.

    This is used by context hydrators and tools like `src` to ensure consistent
    path resolution across shell sessions, threads, and task runners.

    Returns:
        Path: The root path previously set by `set_project_root()`, or the original cwd().
    """
    return _PROJECT_ROOT

def is_git_dirty() -> bool:
    """Return True if there are uncommitted changes in the working directory."""
    from olive.context.utils import get_git_diff_stats
    return bool(get_git_diff_stats())


def get_resource_path(module_name: str, filename: Optional[str] = None) -> Path:
    """
    Resolve a file path relative to the installed location of a Python module.

    Supports editable installs and namespace packages (PEP 420).

    Args:
        module_name (str): Name of the module to locate (e.g. 'olive').
        filename (Optional[str]): Optional file path relative to the module root.

    Returns:
        Path: Fully resolved path to the requested file or module directory.

    Raises:
        ImportError: If the module cannot be located.
    """
    spec = importlib.util.find_spec(module_name)
    if not spec:
        raise ImportError(f"Cannot locate module {module_name}")

    if spec.origin:
        module_path = Path(spec.origin).parent
    elif spec.submodule_search_locations:
        module_path = Path(list(spec.submodule_search_locations)[0])
    else:
        raise ImportError(f"Cannot locate module root for {module_name}")

    return module_path / filename if filename else module_path
