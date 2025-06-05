"""
CLI glue for interacting with the Olive sandbox from inside the REPL / GUI.

Commands registered here are invoked with leading colons, e.g.

    :sandbox-start   – build + start container
    :sandbox-logs    – stream logs
    :sandbox-attach  – attach to tmux inside container
"""

from __future__ import annotations

import subprocess
from typing import Any

from rich.markdown import Markdown

from olive.logger import get_logger
from olive.prompt_ui import olive_management_command
from olive.sandbox import sandbox
from olive.ui import console

from .utils import docker_ready

logger = get_logger("sandbox")

# ───────────────────────── helpers ──────────────────────────
def _docker_stats(name: str) -> tuple[str, str] | tuple[None, None]:
    """Return (cpu%, mem) for the container or (None,None) if stats unavailable."""
    try:
        output = subprocess.check_output(
            [
                "docker",
                "stats",
                "--no-stream",
                "--format",
                "{{.CPUPerc}};{{.MemUsage}}",
                name,
            ],
            text=True,
        ).strip()
        cpu, mem = (x.strip() for x in output.split(";"))
        return cpu, mem
    except subprocess.CalledProcessError:
        return None, None


# ───────────────────────── commands ─────────────────────────
@olive_management_command(":sandbox")
@docker_ready
def sandbox_status_command() -> None:
    """Show status of the Olive sandbox container."""
    logger.info("Queried sandbox status.")

    if not sandbox.is_running():
        console.print("[yellow]Sandbox is not running.[/yellow]")
        return

    console.print("[bold green]🟢 Sandbox is running[/bold green]")
    console.print(f"[bold]Container:[/bold] {sandbox.container_name}")

    cpu, mem = _docker_stats(sandbox.container_name)
    if cpu and mem:
        console.print(f"[bold]CPU:[/bold] {cpu}")
        console.print(f"[bold]Memory:[/bold] {mem}")


@olive_management_command(":sandbox-start")
@docker_ready
def sandbox_start_command(*args: Any) -> None:
    """Start the Olive sandbox container. Use `:sandbox-start --force` to rebuild the image."""
    force_build = "--force" in args
    logger.info("Starting sandbox (force=%s)", force_build)

    try:
        sandbox.start(force_build=force_build)
        if sandbox.is_running():
            console.print("[bold green]✅ Sandbox started successfully.[/bold green]")
        else:
            console.print(
                "[bold red]❌ Sandbox container exited or failed to start.[/bold red]\n"
                "[dim]Use `!docker ps -a` and `!docker logs` for details.[/dim]"
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error while starting sandbox.")
        console.print(
            f"[bold red]❌ Failed to start sandbox: {exc}[/bold red]\n"
            "[dim]Try `--force` to rebuild from scratch.[/dim]"
        )


@olive_management_command(":sandbox-stop")
@docker_ready
def sandbox_stop_command() -> None:
    """Stop and remove the Olive sandbox container."""
    if not sandbox.is_running():
        raise RuntimeError("Sandbox is not running.")

    logger.info("Stopping sandbox.")
    sandbox.stop()
    console.print("[yellow]Sandbox stopped.[/yellow]")


@olive_management_command(":sandbox-restart")
@docker_ready
def sandbox_restart_command() -> None:
    """Restart the Olive sandbox container."""
    if not sandbox.is_running():
        raise RuntimeError("Sandbox is not running.")

    logger.info("Restarting sandbox.")
    sandbox.restart()
    console.print("[cyan]Sandbox restarted.[/cyan]")


@olive_management_command(":sandbox-logs")
@docker_ready
def sandbox_logs_command() -> None:
    """Stream recent logs from the sandbox container (Ctrl-C to quit)."""
    if not sandbox.is_running():
        raise RuntimeError("Sandbox is not running.")

    logger.info("Streaming sandbox logs.")
    console.print("[bold]Tailing sandbox logs… Press Ctrl+C to stop.[/bold]")

    try:
        subprocess.run(
            ["docker", "logs", "--follow", "--tail", "100", sandbox.container_name],
            check=True,
        )
    except subprocess.CalledProcessError as exc:  # noqa: BLE001
        console.print(f"[red]❌ Failed to stream logs: {exc}[/red]")


@olive_management_command(":sandbox-attach")
@docker_ready
def sandbox_attach_command() -> None:
    """Attach to the sandbox tmux session (Ctrl+B then D to detach)."""
    if not sandbox.is_running():
        raise RuntimeError("Sandbox is not running.")

    console.print(f"[cyan]Attaching to sandbox container:[/cyan] {sandbox.container_name}")
    console.print(
        "🛡️  [yellow]Reminder:[/yellow] Press [cyan]Ctrl+B, then D[/cyan] to detach."
    )
    try:
        subprocess.run(
            ["docker", "exec", "-it", sandbox.container_name, "tmux", "attach"],
            check=True,
        )
    except subprocess.CalledProcessError as exc:  # noqa: BLE001
        console.print(f"[red]❌ Failed to attach: {exc}[/red]")


@olive_management_command(":sandbox-help")
def sandbox_help_command() -> None:
    """Show help for sandbox-related commands."""
    help_md = """
# 🧰 Sandbox Commands

| command | action |
|---------|--------|
| `:sandbox` | Show status |
| `:sandbox-start` | Build & start the sandbox |
| `:sandbox-stop` | Stop and remove it |
| `:sandbox-restart` | Restart the container |
| `:sandbox-logs` | Follow container logs |
| `:sandbox-attach` | Attach via tmux |
| `:sandbox-help` | This help |
"""
    console.print(Markdown(help_md))
