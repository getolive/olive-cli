# olive/doctor/__init__.py
from pathlib import Path
from rich.table import Table
from olive.logger import get_logger
from olive.ui import console, print_error, print_info
from olive.canonicals import canonicals_registry
from olive.tools import tool_registry

logger = get_logger(__name__)


def doctor_check(path: str | Path | None = None) -> int:
    """Main Olive diagnostics check (supersedes validate_olive). Returns exit code."""
    project_root = Path(path).expanduser().resolve() if path else Path.cwd().resolve()
    errors = []
    warnings = []
    # 1. Git repo check
    try:
        import subprocess

        subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "--is-inside-work-tree"],
            check=True,
            capture_output=True,
        )
    except Exception:
        errors.append("Not a Git repository.")
    # 2. .olive present
    dot_olive = project_root / ".olive"
    if not dot_olive.exists():
        errors.append("No .olive directory found – did you run `olive init`?")
    # 3. Prefs check (minimal)
    user_pref = Path.home() / ".olive" / "preferences.yml"
    proj_pref = dot_olive / "settings" / "preferences.yml"
    if not (user_pref.exists() or proj_pref.exists()):
        errors.append("Olive requires a preferences.yml to function (user or project).")
    # 4. List tools, canonicals
    tool_registry.discover_all(install=False)
    n_tools = len(tool_registry.list())
    canonicals_registry.discover_all(install=False)
    n_canon = len(canonicals_registry.list())
    # Table summary
    table = Table(title="Olive Doctor", show_header=True, header_style="bold blue")
    table.add_column("Check")
    table.add_column("Status", justify="center")
    table.add_row(
        "Git repository",
        "✅" if not any("Git repository" in e for e in errors) else "❌",
    )
    table.add_row(
        ".olive present", "✅" if not any(".olive" in e for e in errors) else "❌"
    )
    table.add_row(
        "Preferences found",
        "✅" if not any("preferences.yml" in e for e in errors) else "❌",
    )
    table.add_row("Tools discovered", f"{n_tools} 🛠️")
    table.add_row("Canonicals discovered", f"{n_canon} 📄")
    if errors:
        for e in errors:
            print_error(e)
        status = 2
    else:
        print_info("All critical checks passed.")
        status = 0
    console.print(table)
    logger.info(f"Olive doctor result: errors={errors}, warnings={warnings}")

    return status


# validate_olive = doctor_check for legacy import (init.py uses this name)
validate_olive = doctor_check
