"""Olive package bootstrap.

This refactor keeps *import‑time* side‑effects to an absolute minimum so that
merely importing ``olive`` is fast and safe in every environment (REPL, unit
tests, plug‑ins, etc.).  All heavyweight work—filesystem IO, Git checks, CLI
command discovery—now happens lazily inside the dedicated public helpers
``initialize_olive`` and ``initialize_shell_session``.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Sequence, Tuple

from rich.tree import Tree

from olive.logger import get_logger
from olive.ui import console, print_error, print_info, print_warning
from olive.doctor import validate_olive  # re‑export for backwards compatibility
from olive.preferences.admin import get_prefs_lazy

# ---------------------------------------------------------------------------
# Public re‑exports
# ---------------------------------------------------------------------------

__all__: list[str] = [
    "initialize_olive",
    "initialize_shell_session",
    "validate_olive",
]

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants (cheap to evaluate)
# ---------------------------------------------------------------------------

MANDATORY_DOTFILES: Sequence[str] = ("credentials.yml", "preferences.yml")
PROJECT_SUBDIRS: Sequence[str] = (
    "logs",
    "state",
    "specs",
    "context",
    "canonicals",
    "providers",
    "settings",  # per‑project overrides live here
)

# ---------------------------------------------------------------------------
# Lightweight helpers (no heavy IO at import time)
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
# CLI registration (deferred until explicitly asked for)
# ---------------------------------------------------------------------------


def _register_cli_commands() -> None:
    """Import sub‑modules that register Typer/Click commands via side‑effects."""
    from olive import env

    modules = [
        "olive.canonicals.admin",
        "olive.context.admin",
        "olive.sandbox.admin",
        "olive.tasks.admin",
    ]

    prefs = get_prefs_lazy()
    if not env.is_in_sandbox() and prefs.is_voice_enabled():
        modules.append("olive.voice.admin")

    for mod in modules:
        importlib.import_module(mod)


# ---------------------------------------------------------------------------
# Machine‑level (~/.olive) bootstrap
# ---------------------------------------------------------------------------


def _ensure_user_olive(user_root: Path | None = None) -> Tuple[List[str], List[str]]:
    """Ensure *~/.olive* exists and is populated from *dotfile_defaults*.

    Returns ``(copied, skipped)`` lists for UX reporting.
    """
    from olive import env  # local to keep global import cost low

    copied: List[str] = []
    skipped: List[str] = []

    user_root = user_root or env.get_user_root()

    user_root.mkdir(parents=True, exist_ok=True)

    # extract defaults lazily; path is valid only inside the context manager
    with env.get_resource_path("olive", "dotfile_defaults") as defaults:
        for item in defaults.iterdir():
            target = user_root / item.name
            if target.exists():
                skipped.append(item.name)
                continue
            _copy_tree(item, target)
            copied.append(item.name + ("/" if item.is_dir() else ""))
    return copied, skipped


# ---------------------------------------------------------------------------
# Project‑level (.olive) bootstrap
# ---------------------------------------------------------------------------


def _sync_project_settings(
    user_root: Path | None = None, dot_olive: Path | None = None
) -> Tuple[List[str], List[str]]:
    """Sync *~/.olive/* into *project_root/.olive/settings/* once.

    Only copies files that do **not** already exist in the destination so
    local changes are never overwritten.
    """
    from olive import env  # local to keep global import cost low

    copied: List[str] = []
    skipped: List[str] = []

    user_root = user_root or env.get_user_root()
    dot_olive = dot_olive or env.get_dot_olive()

    proj_settings = dot_olive / "settings"
    proj_settings.mkdir(parents=True, exist_ok=True)

    for item in user_root.iterdir():
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


def _require_prefs(user_root: Path, dot_olive: Path) -> None:
    """Abort if no *preferences.yml* exists in user or project settings."""
    user_pref = user_root / "preferences.yml"
    proj_pref = dot_olive / "settings" / "preferences.yml"

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

    # summary of preferences
    from olive.preferences.admin import prefs_show_summary

    prefs_show_summary()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def initialize_olive(path: str | Path | None = None, dry_run: bool = False) -> None:
    """Bootstrap or re‑hydrate an Olive installation.

    This should be the *first* call in any CLI command before deeper Olive
    APIs are touched.  It is intentionally idempotent and cheap on the fast
    path (no work done if everything is already in place).
    """

    from olive import env
    from olive.context import context
    from olive.canonicals import canonicals_registry
    from olive.tools import tool_registry

    project_root = Path(path).expanduser().resolve() if path else Path.cwd().resolve()
    env.set_project_root(project_root)  # make globally visible early

    # 1. Git guard – fail‑fast so users know to `git init`.
    if not _git_is_repo(project_root):
        print_error("Olive requires a Git repository (run `git init`).")
        sys.exit(1)

    # 2. CLI command registration (done once per process)
    _register_cli_commands()

    # 3. Machine‑level bootstrap
    user_root = env.get_user_root()
    copied_user, _skipped_user = _ensure_user_olive(user_root)

    # 4. Project‑level bootstrap
    dot_olive = env.get_dot_olive()
    for sub in PROJECT_SUBDIRS:
        (dot_olive / sub).mkdir(parents=True, exist_ok=True)

    copied_proj, _skipped_proj = _sync_project_settings(user_root, dot_olive)

    # 5. First‑run hint for creds & prefs
    for mandatory in MANDATORY_DOTFILES:
        if mandatory in copied_user:
            print_warning(f"Edit `~/.olive/{mandatory}` with provider credentials.")
        elif mandatory in copied_proj:
            print_warning(f"Edit `.olive/settings/{mandatory}` for project overrides.")

    # 6. Hydrate runtime context & discover dynamic components
    context.hydrate()
    canonicals_registry.discover_all(install=(not dry_run))
    tool_registry.discover_all(install=(not dry_run))

    # 7. Validation
    _require_prefs(user_root, dot_olive)

    # 8. Nice summary
    _render_summary(project_root, copied_user, copied_proj)

    logger.info("Olive initialisation complete.")


# ---------------------------------------------------------------------------
# Interactive‑shell bootstrap (unchanged API)
# ---------------------------------------------------------------------------


def initialize_shell_session() -> None:
    """Emit banner, prefs summary, tool inventory and sandbox status."""
    from olive import env
    from olive.preferences.admin import get_prefs_lazy
    from olive.sandbox import sandbox
    from olive.tools import tool_registry

    # fresh session ID for every shell
    sid = env.generate_session_id()
    console.print(f"[bold green]🌱 Welcome to Olive Shell ({str(sid)})[/bold green]\n")

    prefs = get_prefs_lazy()

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

    # git‑dirty hint
    if env.is_git_dirty():
        print_info(
            "\nFYI: your Git repo has uncommitted changes "
            "(run !git diff from the shell to review).\n"
        )

    # optional sandbox spin‑up
    if prefs.is_sandbox_enabled():
        if not sandbox.is_running():
            try:
                sandbox.start()
                console.print("Sandbox started: ")
            except Exception as exc:
                print_error(f"Failed to start sandbox: {exc}")
                return
        console.print(f"[dim]sandbox session: {env.get_session_id()}[/dim]\n")

    # Kick‑off background init as soon as admin.py is imported
    if prefs.get("voice", "enabled") and not env.is_in_sandbox():
        from olive.voice import runtime as voice_runtime

        try:
            voice_runtime.ensure_ready()
            print_info("[bold]Voice Mode is enabled and ready.[/bold]\n")
            logger.info("voice bootstrap succeeded")
        except Exception as exc:
            print_error(f"Voice Mode failed to ready itself: {exc}\n")
            logger.debug("voice bootstrap failed", exc_info=True)
