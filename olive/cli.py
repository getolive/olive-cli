# cli/olive/cli.py
import typer
import sys
import uuid
import subprocess
from olive.shell import run_interactive_shell, run_shell_command
from olive.init import initialize_olive, validate_olive
from olive.tools.admin import tools_summary_command
from olive.tasks.runner import run_task_from_file
from olive.daemon import process_manager
from olive.context import context

app = typer.Typer(help="Olive: Local AI Dev Shell")

# Global flags container
global_flags = {"daemon": False}


@app.callback()
def main_callback(
    ctx: typer.Context,
    daemon: bool = typer.Option(
        False,
        "--daemon",
        help="Run Olive in background (daemon mode)",
        is_eager=True,
        show_default=False,
    ),
):
    global_flags["daemon"] = daemon


@app.command()
def init():
    """Initialize Olive in the current directory."""
    initialize_olive()


@app.command()
def shell(
    command: str = typer.Option(
        None, "-c", help="Run a single Olive shell command and exit."
    ),
):
    """
    Start the Olive shell interactively or execute a one-off command via `-c`.

    Supports background daemon mode (via `--daemon`) or runs the command immediately.
    """
    initialize_olive()

    if command:
        import asyncio

        result = asyncio.run(run_shell_command(command))
        if result:
            print(result)
        raise typer.Exit()

    if global_flags["daemon"]:
        daemon_id = f"olive-shell-{uuid.uuid4().hex[:6]}"
        process_info = process_manager.spawn(
            daemon_id=daemon_id,
            cmd=[sys.executable, "-m", "olive", "shell"],
            type="shell",
        )
        if process_info:
            typer.echo(
                f"[daemon] Olive shell started in background with daemon ID {daemon_id}."
            )
        else:
            typer.echo("Failed to start Olive shell in daemon mode.")
        raise typer.Exit()
    else:
        import asyncio

        asyncio.run(run_interactive_shell())


@app.command("context")
def context_command():
    """Show the current active context files and tail of active.json."""
    from olive.context.admin import show_context_summary

    show_context_summary()


@app.command("context-files")
def context_files_command():
    """Dump full content of all files marked for inclusion in context to stdout."""
    payload = context._build_context_payload()
    print(payload)


@app.command("reset-cache")
def reset_cache_command():
    """Clear the context file hash cache."""
    from olive.context.admin import reset_context_cache

    reset_context_cache()


@app.command("context-dump")
def context_dump_command():
    """Dump full context payload to a temporary file for inspection."""
    from olive.context.admin import dump_context

    dump_context()


@app.command("validate")
def validate_command():
    """Validate the Olive setup and configuration."""
    validate_olive()


@app.command("tools")
def tools_command():
    """Show available tools and their status."""
    initialize_olive()
    tools_summary_command()


def print_daemon_list(include_dead: bool = False):
    entries = process_manager.list()
    if not entries:
        typer.echo("No active daemons found.")
        raise typer.Exit()
    for daemon_id, proc in entries.items():
        alive = proc.is_alive()
        if not include_dead and not alive:
            continue
        status = "alive" if alive else "dead"
        typer.echo(f"[{daemon_id}] type={proc.type} pid={proc.pid} status={status}")


@app.command("ps")
def ps_command(
    all: bool = typer.Option(False, "-a", help="Show all daemons including dead ones"),
):
    """List background Olive daemons."""
    print_daemon_list(include_dead=all)


@app.command("prune")
def prune_command():
    """Remove all dead Olive daemon daemons."""
    entries = process_manager.list()
    removed = 0
    for daemon_id, proc in entries.items():
        if not proc.is_alive():
            proc.delete()
            removed += 1
    typer.echo(f"Removed {removed} dead daemon(s).")


@app.command("resume")
def resume_command(daemon_id: str = typer.Argument(None)):
    """Resume interaction with a background daemon."""
    if not daemon_id:
        typer.echo(
            "Please specify a daemon ID. Run `olive ps` to view running daemons."
        )
        raise typer.Exit()

    proc = process_manager.get(daemon_id)
    if not proc:
        typer.echo(f"No such daemon: {daemon_id}")
        raise typer.Exit()

    typer.echo(f"Attaching to Olive shell session (daemon ID {daemon_id})...")
    try:
        subprocess.run(["tmux", "attach-session", "-t", daemon_id], check=True)
    except subprocess.CalledProcessError as e:
        typer.echo(f"Failed to attach to tmux session: {e}")


@app.command("kill")
def kill_command(daemon_id: str = typer.Argument(...)):
    """Kill a background daemon by ID."""
    success = process_manager.kill(daemon_id)
    if success:
        typer.echo(f"Killed daemon {daemon_id}")
    else:
        typer.echo(f"Failed to kill or locate daemon {daemon_id}")


@app.command("run-task")
def run_task_command(
    task_file: str,
    json: bool = typer.Option(False, "--json", help="Emit only raw JSON"),
):
    """
    Execute a task spec from a file (used by sandbox or headless execution).
    """
    initialize_olive()
    from olive.tools import tool_registry

    tool_registry.discover_all(install=False)
    if json:
        # return the JSON blob directly
        payload = run_task_from_file_json(task_file)
        typer.echo(payload)
    else:
        run_task_from_file(task_file)
