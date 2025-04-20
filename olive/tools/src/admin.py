# cli/olive/tools/src/admin.py

"""
Management commands for the src tool (e.g., :diff).
"""

import shlex
import subprocess
from shutil import which

from rich import print

from olive.logger import get_logger  # fixed import
from olive.prompt_ui import olive_management_command

logger = get_logger("tools.src.admin")  # more specific name


@olive_management_command(":diff")
def diff_command(args: str = None):
    """Show uncommitted git changes. Accepts optional path filter."""
    path_args = shlex.split(args or "")
    pager = which("less") or which("more")

    cmd = ["git", "diff", "--color=always"] + path_args
    logger.info(f"Running diff command: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        output = result.stdout

        if not output.strip():
            print("[green]✅ No uncommitted changes.[/green]")
            return

        if pager:
            subprocess.run([pager, "-R"], input=output, text=True)
        else:
            print(output)

    except subprocess.CalledProcessError as e:
        print(f"[red]Error running git diff: {e}[/red]")
        logger.exception("Git diff failed")
