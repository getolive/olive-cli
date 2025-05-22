"""
olive.init – project boot‑strapper for Olive CLI
===============================================
This module is the single canonical place responsible for **creating**,
**validating** and **displaying** the state of an Olive installation.

It fulfils six key requirements (see PR‑spec):

1. `initialize_olive(path: str | Path | None = None)` may be invoked from
   any working directory or test harness to bootstrap Olive in *path*.
2. Ensures **machine‑level** config at *~/.olive* by copying bundled
   `dotfile_defaults/*` once. Prompts the user to edit
   `credentials.yml` and `preferences.yml` if they are brand‑new.
3. Creates / refreshes **project‑level** config at
   `<project_root>/.olive` including a **settings/** folder that shadows
   `~/.olive` for per‑project overrides.
4. Exposes two public, dependency‑free helpers – `initialize_olive()` and
   `validate_olive()` – suitable for CLI entrypoints *and* isolated unit
   tests (call inside a `tmp_path`).
5. Performs rigorous validation (Git repo, prefs, context etc.) and
   raises or exits cleanly with actionable Rich messages.
6. Presents a minimal, information‑dense TUI summary after init / shell
   start‑up so operators instantly know the health of their Olive.

The implementation keeps backwards compatibility with the previous API
so existing CLI commands (`olive init`, `olive shell` …) keep working
unchanged.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Sequence, Tuple

from rich.table import Table
from rich.tree import Tree

from olive import env
import olive.canonicals.admin  # noqaF401 side‑effect: register CLI commands  # type: ignore
import olive.context.admin  # noqa:F401 side‑effect: register CLI commands
import olive.sandbox.admin  # noqa:F401 side‑effect: register CLI commands
import olive.tasks.admin  # noqa:F401 side‑effect: register CLI commands

from olive.context import context
from olive.canonicals import canonicals_registry
from olive.logger import get_logger
from olive.preferences.admin import prefs_show_summary
from olive.tools import tool_registry
from olive.ui import console, print_error, print_info, print_warning

__all__ = [
    "initialize_olive",
    "initialize_shell_session",
    "validate_olive",
]

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Low‑level helpers
# ---------------------------------------------------------------------------


def _git_is_repo(path: Path) -> bool:
    """Return *True* if *path* (or any parent) is a Git repo."""
    try:
        subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def _copy_tree(src: Path, dst: Path) -> None:
    """Recursively copy *src* → *dst*; never overwrites existing files."""
    if src.is_dir():
        dst.mkdir(parents=True, exist_ok=True)  # ensure empty dirs survive
        for item in src.iterdir():
            _copy_tree(item, dst / item.name)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            shutil.copy2(src, dst)


# ---------------------------------------------------------------------------
# Machine‑level (~/.olive) bootstrap
# ---------------------------------------------------------------------------

DOTFILE_DEFAULTS = env.get_resource_path("olive", "dotfile_defaults")
USER_OLIVE = env.get_user_root()
MANDATORY_DOTFILES: Sequence[str] = ("credentials.yml", "preferences.yml")


def _ensure_user_olive() -> Tuple[List[str], List[str]]:
    """Ensure *~/.olive* exists and is populated from *dotfile_defaults*.

    Returns a tuple ``(copied, skipped)`` with base‑name strings for UX
    reporting.
    """
    copied: List[str] = []
    skipped: List[str] = []

    USER_OLIVE.mkdir(parents=True, exist_ok=True)

    for item in DOTFILE_DEFAULTS.glob("*"):
        target = USER_OLIVE / item.name
        if target.exists():
            skipped.append(item.name)
            continue
        _copy_tree(item, target)
        copied.append(item.name + ("/" if item.is_dir() else ""))
    return copied, skipped


# ---------------------------------------------------------------------------
# Project‑level (.olive) bootstrap
# ---------------------------------------------------------------------------

PROJECT_SUBDIRS: Sequence[str] = (
    "logs",
    "state",
    "specs",
    "context",
    "canonicals",
    "providers",
    "settings",  # ← per‑project overrides live here
)


def _sync_project_settings() -> Tuple[List[str], List[str]]:
    """Sync *~/.olive/* into *project_root/.olive/settings/* once.

    Only copies files that do **not** already exist in the destination
    so local changes are never overwritten.
    """
    copied: List[str] = []
    skipped: List[str] = []

    proj_settings = env.get_dot_olive() / "settings"
    proj_settings.mkdir(parents=True, exist_ok=True)

    for item in USER_OLIVE.glob("*"):
        if item.is_dir() or item.name == "settings":
            continue
        dst = proj_settings / item.name
        if dst.exists():
            skipped.append(item.name)
            continue
        _copy_tree(item, dst)
        copied.append(item.name + ("/" if item.is_dir() else ""))
    return copied, skipped


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _require_prefs() -> None:
    """
    Abort if **neither**
        ~/.olive/preferences.yml     nor
        .olive/settings/preferences.yml
    exists.  (Content validity is checked later by the prefs subsystem.)
    """
    user_pref = USER_OLIVE / "preferences.yml"
    proj_pref = env.get_dot_olive() / "settings" / "preferences.yml"

    if user_pref.exists() or proj_pref.exists():
        return

    print_error("Olive requires a preferences.yml to function.")
    print_info(
        "Create *preferences.yml* either in ~/.olive or .olive/settings "
        "and rerun `olive init`."
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Rich UI helpers
# ---------------------------------------------------------------------------


def _render_summary(
    project_root: Path, copied_user: Sequence[str], copied_proj: Sequence[str]
) -> None:
    """Pretty TUI after initialisation / validation."""
    tree = Tree(f"Initialized Olive @ [bold]{project_root}[/]")

    # ── dotfiles
    dot = tree.add("[bold cyan]~/.olive[/]")
    dot.add(f"[green]copied[/]: {', '.join(copied_user) or '–'}")

    # ── project .olive
    proj = tree.add("[bold cyan].olive[/]")
    proj.add(f"sub‑dirs: {', '.join(PROJECT_SUBDIRS)}")
    proj.add(f"settings copied: {', '.join(copied_proj) or '–'}")

    console.print(tree)
    prefs_show_summary()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def initialize_olive(path: str | Path | None = None) -> None:
    """Bootstrap or re‑hydrate an Olive installation.

    Parameters
    ----------
    path
        Optional project root. Defaults to the *current working
        directory* as resolved by :pyfunc:`Path.cwd`.
    """
    project_root = Path(path).expanduser().resolve() if path else Path.cwd().resolve()
    env.set_project_root(project_root)  # make globally visible early

    # 1. Git guard – fail‑fast so users know to `git init`.
    if not _git_is_repo(project_root):
        print_error("Olive requires a Git repository (run `git init`).")
        sys.exit(1)

    # 2. Machine‑level bootstrap
    copied_user, _skipped_user = _ensure_user_olive()

    # 3. Project‑level bootstrap
    dot_olive = env.get_dot_olive()
    for sub in PROJECT_SUBDIRS:
        (dot_olive / sub).mkdir(parents=True, exist_ok=True)

    copied_proj, _skipped_proj = _sync_project_settings()

    # 4. First‑run hint for creds & prefs
    for mandatory in MANDATORY_DOTFILES:
        if mandatory in copied_user:
            print_warning(f"Edit `~/.olive/{mandatory}` with provider credentials.")
        elif mandatory in copied_proj:
            print_warning(f"Edit `.olive/settings/{mandatory}` for project overrides.")

    # 5. Hydrate runtime context & discover dynamic components
    context.hydrate()
    canonicals_registry.discover_all(install=True)
    tool_registry.discover_all(install=True)

    # 6. Validation
    _require_prefs()

    # 7. Nice summary
    _render_summary(project_root, copied_user, copied_proj)

    logger.info("Olive initialisation complete.")


def validate_olive(path: str | Path | None = None) -> None:
    """Run a lightweight health‑check without modifying on‑disk state."""
    project_root = Path(path).expanduser().resolve() if path else Path.cwd().resolve()

    if not _git_is_repo(project_root):
        print_error("Not a Git repository – cannot validate Olive here.")
        sys.exit(1)

    dot_olive = project_root / ".olive"
    if not dot_olive.exists():
        print_error("No .olive directory found – did you run `olive init`?")
        sys.exit(1)

    # prefs & context
    _require_prefs()

    # quick component listing
    n_tools = len(tool_registry.list())
    n_canon = len(canonicals_registry.list())

    table = Table(
        title="Olive Health‑check", show_header=True, header_style="bold blue"
    )
    table.add_column("Check")
    table.add_column("Status", justify="center")

    table.add_row("Git repository", "✅")
    table.add_row(".olive present", "✅")
    table.add_row("Tools discovered", f"{n_tools} 🛠️")
    table.add_row("Canonicals discovered", f"{n_canon} 📄")

    console.print(table)
    logger.info("Olive validation finished OK.")


# ---------------------------------------------------------------------------
# Interactive-shell bootstrap
# ---------------------------------------------------------------------------


def initialize_shell_session() -> None:
    """
    Emit the Rich welcome banner, preference summary, tool inventory and—
    if enabled—start / display the Docker sandbox session ID.  Used by the
    `olive shell` command and unit-tests.
    """
    from olive.env import generate_session_id, get_session_id, is_git_dirty
    from olive.preferences.admin import get_prefs_lazy
    from olive.sandbox import sandbox

    # fresh session ID for every shell
    generate_session_id()
    console.print("[bold green]🌱 Welcome to Olive Shell[/bold green]\n")

    # tool inventory
    tools = tool_registry.list()
    n_tools = len(tools)
    parent = f"Olive has access to {n_tools} tool{'s' if n_tools != 1 else ''}"
    tree = Tree(parent, guide_style="bold cyan")
    for entry in tools:
        name = f"[bold]{entry.tool.name}[/bold]"
        desc = (entry.tool.description or "").splitlines()[0]
        if len(desc) > 80:
            desc = desc[:80] + " […]"
        tree.add(f"{name}: {desc}")
    console.print(tree)

    # git-dirty hint
    if is_git_dirty():
        print_info(
            "\nFYI: your Git repo has uncommitted changes "
            "(run !git diff from the shell to review).\n"
        )

    # optional sandbox spin-up
    prefs = get_prefs_lazy()
    if prefs.is_sandbox_enabled():
        if not sandbox.is_running():
            try:
                sandbox.start()
            except Exception as exc:
                print_error(f"Failed to start sandbox: {exc}")
                return
        console.print(f"[dim]sandbox session: {get_session_id()}[/dim]\n")
