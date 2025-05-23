# cli/olive/preferences/admin.py
import subprocess
from shutil import which

from rich.panel import Panel
from rich.tree import Tree

from olive.logger import get_logger
from olive.prompt_ui import olive_management_command

from olive.ui import console, print_info, print_error

logger = get_logger(__name__)


def get_prefs_lazy():
    from olive.preferences import prefs
    return prefs


ESSENTIAL_KEYS = [
    ("context.system_prompt_path", "System Prompt Path"),
    ("context.respect_gitignore", "Respect .gitignore"),
    ("context.max_tokens", "Max Tokens"),
    ("context.max_files", "Max Files"),
    ("context.include.patterns", "Include Patterns"),
    ("context.exclude.patterns", "Exclude Patterns"),
    ("builder_mode.autonomy", "Builder Autonomy"),
    ("builder_mode.confidence_threshold", "Confidence Threshold"),
    ("ai.model", "AI Model"),
    ("sandbox.enabled", "Sandbox Enabled"),
    ("code_smells.enabled", "Code Smells Enabled"),
]


def get_from_dotpath(prefs, dotpath):
    return prefs.get(*dotpath.split("."), default=None)


@olive_management_command(":prefs")
def prefs_show_summary(*args, **kwargs):
    """\
    Show Olive preference summary. (:prefs --full --> show all preferences in a tree)
    """
    full = "--full" in args
    no_pager = "--no-pager" in args

    prefs = get_prefs_lazy()
    prefs_path, exists = prefs.get_preferences_path()

    if not exists:
        print_error(f"Preferences not found at {prefs_path}")
        return

    console.print(
        Panel.fit(
            f"[primary]Olive Preferences[/primary]\n[info]{prefs_path}[/info]",
            title=f"Active Preferences ({'Full' if full else 'Abridged'})",
        )
    )

    if full:
        tree = Tree("🌳 [bold green]Full Preferences Tree[/bold green]")

        def add_subtree(branch, node):
            if isinstance(node, dict):
                for key, val in node.items():
                    sub = branch.add(f"[bold]{key}[/bold]")
                    add_subtree(sub, val)
            elif isinstance(node, list):
                for i, item in enumerate(node):
                    item_repr = (
                        f"[{i}] {item}" if not isinstance(item, dict) else f"[{i}]"
                    )
                    sub = branch.add(item_repr)
                    if isinstance(item, dict):
                        add_subtree(sub, item)
            else:
                branch.add(f"[dim]=[/dim] {node}")

        add_subtree(tree, prefs.prefs)

        pager = which("less") or which("more")
        try:
            if pager and not no_pager:
                output = console.export_text(tree)
                subprocess.run([pager, "-R"], input=output, text=True)
            else:
                console.print(tree)
        except Exception:
            console.print(tree)
    else:
        tree = Tree("🌿 [bold green]Essential Preferences[/bold green]")
        for dotpath, label in ESSENTIAL_KEYS:
            val = get_from_dotpath(prefs, dotpath)
            display_val = str(val) if val is not None else "[grey50]—[/grey50]"
            tree.add(f"[bold]{label}[/bold]: {display_val}")

        console.print(tree)
        print_info(
            "\nTip: Run [primary]:prefs --full[/primary] to view the complete preference tree."
        )
