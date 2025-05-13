# cli/olive/init.py
import json
import subprocess
from pathlib import Path

import olive.canonicals.admin  # Register CLI commands # type: ignore
import olive.context.admin  # Register CLI commands # type: ignore
import olive.sandbox.admin  # Register CLI commands # type: ignore
import olive.tasks.admin  # Register CLI commands # type: ignore
from olive.canonicals import canonicals_registry
from olive.context import context
from olive import env
from olive.logger import get_logger
from olive.preferences.admin import get_prefs_lazy, prefs_show_summary
from olive.tools import tool_registry
from olive.tools.admin import tools_summary_command
from olive.ui import console, print_info, print_error, print_success, print_warning
from rich.tree import Tree

logger = get_logger(__name__)


def load_system_prompt(prefs) -> str:
    """Load the system prompt from a path specified in prefs, or fallback to default."""
    prompt_path = Path(
        prefs.get(
            "context", "system_prompt_path", default="~/.olive/my_system_prompt.txt"
        )
    ).expanduser()

    if prompt_path.exists():
        logger.info(f"Loaded system prompt from {prompt_path}")
        return prompt_path.read_text()

    logger.warning("Using fallback system prompt")
    return (
        "You are Olive — a local-first, developer-facing, intelligent CLI agent. You are being used by your creator to build and improve yourself. "
        "You operate entirely on the user's machine and respect privacy by default. You do not assume cloud access unless explicitly configured. Your mission is to help your user manage time, coordinate tasks, build systems, and create leverage — starting with yourself. "
        "You live inside a Typer-based CLI application. You use context files, preferences, and user instructions to interact intelligently. "
        "This is your context. Build wisely. Collaborate deeply. Minimize friction. Maximize momentum."
    )


def validate_git_repo():
    try:
        subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            check=True,
            capture_output=True,
        )
        logger.info("Git repository detected")
        return True
    except subprocess.CalledProcessError:
        print_error("Olive requires a Git repository.")
        print_info("Please run `git init` and try again.")
        logger.error("Git repository not found.")
        return False


def ensure_directories():
    base = env.get_dot_olive()
    for sub in ["logs", "context", "canonicals", "providers", "state"]:
        (base / sub).mkdir(parents=True, exist_ok=True)
    logger.info("Required directories ensured")


def ensure_context_initialized(prefs):
    context_path = env.get_dot_olive() / "context" / "active.json"
    if not context_path.exists():
        context = {
            "system_prompt": load_system_prompt(prefs),
            "chat": [],
            "files": [],
            "metadata": {},
        }
        context_path.write_text(json.dumps(context, indent=2))
        logger.info("Created new .olive/context/active.json")
    else:
        logger.info("Using existing .olive/context/active.json")


def discover_components():
    try:
        canonicals_registry.discover_all(install=True)
        logger.info("Canonicals discovered and installed")
    except Exception as e:
        logger.warning(f"Canonicals discovery failed: {e}")

    try:
        tool_registry.discover_all(install=True)
        logger.info("Tools discovered and installed")
    except Exception as e:
        logger.warning(f"Tools discovery failed: {e}")


def start_sandbox_if_enabled(prefs) -> bool:
    if prefs.is_sandbox_enabled():
        try:
            olive.sandbox.admin.sandbox_start_command()
            logger.info("Sandbox started")
            return True
        except Exception as e:
            logger.error(f"Failed to start sandbox: {e}")
            print_error("Failed to start sandbox — exiting shell.")
            raise SystemExit(1)
    else:
        return False


def initialize_shell_session():
    from olive.env import generate_session_id, get_session_id

    generate_session_id()

    console.print("[bold green]🌱 Welcome to Olive Shell[/bold green]\n")

    prefs_show_summary()

    tools = tool_registry.list()
    n_tools = len(tools)
    parent_label = f"Olive has access to {n_tools} tool{'s' if n_tools != 1 else ''}"
    tool_tree = Tree(parent_label, guide_style="bold cyan")

    for entry in tools:
        tool_name = f"[bold]{entry.tool.name}[/bold]"
        desc = (entry.tool.description or "").splitlines()[0]
        if len(desc) > 80:
            desc = desc[:80] + " [...]"
        tool_tree.add(f"{tool_name}: {desc}")

    console.print(tool_tree)
    if env.is_git_dirty():
        print_info(
            "\nFYI: your git repo is dirty (uncommitted changes detected, you can run !git diff from shell to review))\n"
        )

    prefs = get_prefs_lazy()
    sandbox_started = start_sandbox_if_enabled(prefs)
    if sandbox_started:
        console.print(f"[dim]sandbox session: {get_session_id()}[/dim]\n")


def validate_olive():
    """Validates user/project Olive configuration and context."""
    try:
        initialize_olive()
        print_success("Olive has been initialized\n")
    except Exception as e:
        print_error(f"Olive failed to initialize. [dim]{str(e)}[/dim]")
        logger.exception("Initialization failed")
        return

    user_path = Path.home() / ".olive"
    project_path = Path(".olive")
    gitignore_path = Path(".gitignore")

    print_info("\n📂 [bold underline]User Olive Directory (~/.olive):[/bold underline]")
    console.print(
        f"✅ Found {user_path}"
        if user_path.exists()
        else "❌ Missing ~/.olive directory"
    )

    print_info(
        "\n📁 [bold underline]Project Olive Directory (.olive):[/bold underline]"
    )
    if project_path.exists():
        print_success(f"✅ Found {project_path}")

        logs = project_path / "logs"
        if logs.exists():
            size_kb = (
                sum(f.stat().st_size for f in logs.glob("*") if f.is_file()) / 1024
            )
            print_success(f"Logs present — {size_kb:.1f} KB")
        else:
            print_error("⚠️ Missing logs directory")

        context = project_path / "context" / "active.json"
        console.print(
            "✅ Context loaded" if context.exists() else "⚠️ Missing active.json"
        )

        print_info("\n🔍 Canonicals:")
        canonicals = sorted(canonicals_registry.list())
        if canonicals:
            for name in canonicals:
                print_success(f"{name}")
        else:
            print_warning("⚠️ No canonicals found")

        print_info("\n🛠️ Tools:")
        tools_summary_command()
    else:
        print_error("Missing .olive directory")

    print_info("\n📄 [bold underline].gitignore Checks:[/bold underline]")
    if gitignore_path.exists():
        lines = gitignore_path.read_text().splitlines()
        ignored = any(".olive/" in line or ".olive/*" in line for line in lines)
        override = any("!.olive/specs/" in line for line in lines)
        console.print(
            "✅ `.olive/` is ignored" if ignored else "❌ Missing `.olive/` ignore line"
        )
        console.print(
            "✅ `.olive/specs/` is tracked"
            if override
            else "❌ Missing `!.olive/specs/` override"
        )
    else:
        print_error("⚠️ No .gitignore file found")


def initialize_olive():
    project_root_path = Path.cwd().resolve()
    logger.info(f"Starting Olive initialization @ {project_root_path}")
    env.set_project_root(project_root_path)

    if not validate_git_repo():
        return

    prefs = get_prefs_lazy()
    if not prefs.initialized:
        print_error("Olive requires a preferences.yml to function.")
        print_info("Please create ~/.olive/preferences.yml and retry.")
        logger.error("Preferences not initialized.")
        return

    ensure_directories()
    context.hydrate()
    discover_components()

    print_success("Initialized Olive in .olive/")
    logger.info("Initialization complete.")
