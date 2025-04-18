# cli/olive/init.py
import json
import subprocess
from pathlib import Path

from rich import print
from rich.console import Console

from olive.logger import get_logger
from olive.env import get_olive_base_path, set_project_root, is_git_dirty
from olive.preferences.admin import get_prefs_lazy, prefs_show_summary
from olive.canonicals import canonicals_registry
from olive.tools import tool_registry
from olive.tools.admin import tools_summary_command
import olive.sandbox.admin  # Register CLI commands # type: ignore
import olive.tasks.admin  # Register CLI commands # type: ignore
import olive.canonicals.admin  # Register CLI commands # type: ignore
import olive.context.admin  # Register CLI commands # type: ignore

from olive.context import context

logger = get_logger(__name__)
console = Console()


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
        print("[red]❌ Olive requires a Git repository.[/red]")
        print("Please run `git init` and try again.")
        logger.error("Git repository not found.")
        return False


def ensure_directories():
    base = get_olive_base_path()
    for sub in ["logs", "context", "canonicals", "providers", "state"]:
        (base / sub).mkdir(parents=True, exist_ok=True)
    logger.info("Required directories ensured")


def ensure_context_initialized(prefs):
    context_path = get_olive_base_path() / "context" / "active.json"
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


def start_sandbox_if_enabled(prefs):
    if prefs.is_sandbox_enabled():
        with console.status(
            "[bold green]Starting sandbox...[/bold green]", 
            spinner="dots"
        ):
            try:
                olive.sandbox.admin.sandbox_start_command()
                logger.info("Sandbox started")
            except Exception as e:
                logger.error(f"Failed to start sandbox: {e}")
                print("[red]❌ Failed to start sandbox — exiting shell.[/red]")
                raise SystemExit(1)


def initialize_shell_session():
    from uuid import uuid4
    import olive.env

    olive.env.session_id = str(uuid4())[:8]
    print(
        f"[bold green]🌱 Welcome to Olive Shell[/bold green] [dim](session: {olive.env.session_id})[/dim]\n"
    )

    prefs_show_summary()

    if is_git_dirty():
        print("[yellow]⚠️ Git repo is dirty — uncommitted changes detected[/yellow]\n")

    prefs = get_prefs_lazy()
    start_sandbox_if_enabled(prefs)


def initialize_olive():
    project_root_path = Path.cwd().resolve()
    logger.info(f"Starting Olive initialization @ {project_root_path}")
    set_project_root(project_root_path)

    if not validate_git_repo():
        return

    prefs = get_prefs_lazy()
    if not prefs.initialized:
        print("[red]❌ Olive requires a preferences.yml to function.[/red]")
        print("Please create ~/.olive/preferences.yml and retry.")
        logger.error("Preferences not initialized.")
        return

    ensure_directories()
    context.hydrate()
    discover_components()

    print("✅ Initialized Olive in .olive/")
    logger.info("Initialization complete.")


def validate_olive():
    """Validates user/project Olive configuration and context."""
    try:
        initialize_olive()
        print("✅ Olive has been initialized\n")
    except Exception as e:
        print(f"[red]❌ Olive failed to initialize.[/red] [dim]{str(e)}[/dim]")
        logger.exception("Initialization failed")
        return

    user_path = Path.home() / ".olive"
    project_path = Path(".olive")
    gitignore_path = Path(".gitignore")

    print("\n📂 [bold underline]User Olive Directory (~/.olive):[/bold underline]")
    print(
        f"✅ Found {user_path}"
        if user_path.exists()
        else "❌ Missing ~/.olive directory"
    )

    print("\n📁 [bold underline]Project Olive Directory (.olive):[/bold underline]")
    if project_path.exists():
        print(f"✅ Found {project_path}")

        logs = project_path / "logs"
        if logs.exists():
            size_kb = (
                sum(f.stat().st_size for f in logs.glob("*") if f.is_file()) / 1024
            )
            print(f"✅ Logs present — {size_kb:.1f} KB")
        else:
            print("⚠️ Missing logs directory")

        context = project_path / "context" / "active.json"
        print("✅ Context loaded" if context.exists() else "⚠️ Missing active.json")

        print("\n🔍 Canonicals:")
        canonicals = sorted(canonicals_registry.list())
        if canonicals:
            for name in canonicals:
                print(f"✅ {name}")
        else:
            print("⚠️ No canonicals found")

        print("\n🛠️ Tools:")
        tools_summary_command()
    else:
        print("❌ Missing .olive directory")

    print("\n📄 [bold underline].gitignore Checks:[/bold underline]")
    if gitignore_path.exists():
        lines = gitignore_path.read_text().splitlines()
        ignored = any(".olive/" in line or ".olive/*" in line for line in lines)
        override = any("!.olive/specs/" in line for line in lines)
        print(
            "✅ `.olive/` is ignored" if ignored else "❌ Missing `.olive/` ignore line"
        )
        print(
            "✅ `.olive/specs/` is tracked"
            if override
            else "❌ Missing `!.olive/specs/` override"
        )
    else:
        print("⚠️ No .gitignore file found")
