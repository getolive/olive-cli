# cli/olive/sandbox/admin.py
import subprocess

from rich.console import Console
from rich.markdown import Markdown

from olive.logger import get_logger
from olive.prompt_ui import olive_management_command
from olive.sandbox import sandbox

from .utils import docker_required

console = Console()
logger = get_logger(__name__)


@olive_management_command(":sandbox")
@docker_required
def sandbox_status_command():
    """Show status of the Olive sandbox container."""
    logger.info("Queried sandbox status.")
    status = sandbox.status()
    if not status.get("running"):
        console.print("[yellow]Sandbox is not running.[/yellow]")
    else:
        console.print("[bold green]🟢 Sandbox is running[/bold green]")
        console.print(f"[bold]Container:[/bold] {status.get('name')}")
        console.print(f"[bold]CPU:[/bold] {status.get('cpu')}")
        console.print(f"[bold]Memory:[/bold] {status.get('mem')}")


@olive_management_command(":sandbox-start")
@docker_required
def sandbox_start_command(*args, **kwargs):
    """Start the Olive sandbox container. Use `:sandbox-start --force` to force a rebuild of the image."""
    force_rebuild = "--force" in args
    logger.info(f"Starting sandbox (force rebuild = {force_rebuild})")

    try:
        sandbox.build(force=force_rebuild)
        sandbox.start()

        if sandbox.is_running():
            console.print("[bold green]✅ Sandbox started successfully.[/bold green]")
        else:
            console.print(
                "[bold red]❌ Sandbox container exited or failed to start.[/bold red]\n"
                "[dim]Use `!docker ps -a` to inspect containers,[/dim]\n"
                "[dim]and `!docker logs <container>` to check for errors.[/dim]"
            )
    except Exception as e:
        logger.exception("Error while starting sandbox.")
        console.print(
            f"[bold red]❌ Failed to start sandbox: {e}[/bold red]\n"
            "[dim]Check logs or try `--force` to rebuild from scratch.[/dim]"
        )


@olive_management_command(":sandbox-stop")
@docker_required
def sandbox_stop_command():
    """Stop and remove the Olive sandbox container."""
    if not sandbox.is_running():
        raise RuntimeError("Sandbox is not running.")

    logger.info("Stopping sandbox.")
    sandbox.stop()
    console.print("[yellow]Sandbox stopped.[/yellow]")


@olive_management_command(":sandbox-restart")
@docker_required
def sandbox_restart_command():
    """Restart the Olive sandbox container."""
    if not sandbox.is_running():
        raise RuntimeError("Sandbox is not running.")

    logger.info("Restarting sandbox.")
    sandbox.restart()
    console.print("[cyan]Sandbox restarted.[/cyan]")


@olive_management_command(":sandbox-logs")
@docker_required
def sandbox_logs_command():
    """Stream recent logs from the sandbox container."""
    if not sandbox.is_running():
        raise RuntimeError("Sandbox is not running.")

    logger.info("Tailing sandbox logs.")
    console.print("[bold]Tailing sandbox logs... Press Ctrl+C to stop.[/bold]")
    sandbox.logs(tail=100, follow=True)


@olive_management_command(":sandbox-attach")
@docker_required
def sandbox_attach_command():
    """\
    Attach interactively to the sandbox tmux session. Detach safely with Ctrl+B then D. Exiting the session will shut down the container.
    """
    if not sandbox.is_running():
        raise RuntimeError("Sandbox is not running.")

    container = sandbox.container_name
    console.print(f"[cyan]Attaching to sandbox container:[/cyan] {container}")
    console.print(
        "🛡️  [yellow]Reminder:[/yellow] Press [cyan]Ctrl+B, then D[/cyan] to detach. [dim]Exiting will stop the container.[/dim]"
    )
    try:
        subprocess.run(
            ["docker", "exec", "-it", container, "tmux", "attach"], check=True
        )
    except subprocess.CalledProcessError as e:
        console.print(f"[red]❌ Failed to attach to sandbox tmux session: {e}[/red]")


@olive_management_command(":sandbox-help")
def sandbox_help_command():
    """Show help for sandbox-related commands."""
    help_text = """\

# 🧰 Sandbox Commands
Manage the Olive sandbox environment:

- `:sandbox` — Show status
- `:sandbox-start` — Start the sandbox container
- `:sandbox-stop` — Stop and remove the container
- `:sandbox-restart` — Restart the container cleanly
- `:sandbox-logs` — Stream recent logs from the sandbox
- `:sandbox-tty` — Attach to the sandbox terminal via tmux
- `:sandbox-help` — Show this help message

"""
    console.print(Markdown(help_text))
