# cli/olive/cli.py
import asyncio
import json
import os
import signal
import subprocess
import sys
import uuid
from pathlib import Path

import typer

from olive import env
from olive.context import context
from olive.daemon import process_manager
from olive.init import initialize_olive, validate_olive
from olive.shell import run_interactive_shell, run_shell_command
from olive.tasks.runner import run_task_from_file
from olive.tools.admin import tools_summary_command

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
        # 1) re‑use existing alive shell
        alive = next(
            (
                p
                for p in process_manager.list().values()
                if p.kind == "shell" and p.is_alive()
            ),
            None,
        )
        if alive:
            sbx_dir = env.get_sandbox_root()
            info = {
                "id": alive.daemon_id,
                "sbx_dir": str(sbx_dir),
                "rpc_dir": str(sbx_dir / "rpc"),
                "result_dir": str(sbx_dir / "result"),
            }
            typer.echo(json.dumps(info))
            raise typer.Exit()

        # 2) spawn fresh daemon
        sid = uuid.uuid4().hex[:8]
        sbx_dir = Path(".olive/run/sbx") / sid
        (sbx_dir / "rpc").mkdir(parents=True, exist_ok=True)
        (sbx_dir / "result" / "logs").mkdir(parents=True, exist_ok=True)

        os.environ["OLIVE_SESSION_ID"] = sid
        os.environ["OLIVE_SANDBOX_DIR"] = str(sbx_dir)

        cmd = [
            "env",
            f"OLIVE_SESSION_ID={sid}",
            f"OLIVE_SANDBOX_DIR={sbx_dir}",
            sys.executable,
            "-m",
            "olive",
            "shell",
        ]

        proc = process_manager.spawn(daemon_id=sid, cmd=cmd, kind="shell")

        if not proc:
            typer.echo("Failed to start daemon")
            raise typer.Exit(1)

        info = {
            "id": sid,
            "sbx_dir": str(sbx_dir),
            "rpc_dir": str(sbx_dir / "rpc"),
            "result_dir": str(sbx_dir / "result"),
            "export": f"export OLIVE_SESSION_ID={sid} "
            f"OLIVE_SANDBOX_DIR='{sbx_dir.resolve()}'",
        }
        typer.echo(json.dumps(info))
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
        typer.echo(f"[{daemon_id}] kind={proc.kind} pid={proc.pid} status={status}")


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


@app.command("attach")
def attach_to_daemon_session(sid: str = typer.Argument(None)):
    """Attach/Resume interaction with a background daemon."""
    def no_match_exit():
        typer.echo(
            "Please specify a daemon ID. Run `olive ps` to view running daemons."
        )
        raise typer.Exit(code=-1)

    entries = process_manager.list()
    session_ids = [sid for sid, proc in entries.items()]

    target_sid = None
    if sid is None:
        if len(session_ids) == 1:
            target_sid = session_ids[0]
        else:
            no_match_exit()
    else:
        matching_sids = [s for s in session_ids if s.startswith(sid)]
        if not matching_sids or len(matching_sids) > 1:
            no_match_exit()
        else:
            target_sid = matching_sids[0]

    proc = process_manager.get(target_sid)
    if not proc:
        typer.echo(f"No such daemon with session id (sid): {sid}")
        raise typer.Exit()

    typer.echo(f"Attaching to Olive shell session {target_sid})...")
    try:
        subprocess.run(["tmux", "attach-session", "-t", target_sid], check=True)
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


@app.command("ask")
def ask_command(
    prompt: str = typer.Argument(..., help="Prompt to send to olive.llm.ask"),
):
    """Tiny wrapper around the LLM helper so other code (and HTTP) can shell out."""
    try:
        from olive.llm import ask as _ask

        print(_ask(prompt))
    except Exception as exc:  # noqa: BLE001
        # graceful degradation – echo back
        typer.echo(f"[stub] You said: {prompt} • (ask unavailable: {exc})")


# ---------------------------------------------------------------------
# Serve HTTP
# ---------------------------------------------------------------------
@app.command("http")
def http(
    host: str = typer.Option("0.0.0.0", "--host"),
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(False, "--reload", "--dev", help="Hot‑reload"),
):
    """Serve the Olive HTTP gateway."""
    # ----------- ensure env defaults -----------------
    os.environ.setdefault("OLIVE_HTTP_HOST", host)
    os.environ.setdefault("OLIVE_HTTP_PORT", str(port))
    os.environ.setdefault(
        "OLIVE_HTTP_ALLOW_CMDS", "tools,tasks,task-run,task-get,context,ask"
    )

    import uvicorn

    cfg = uvicorn.Config(
        "olive.http:app", host=host, port=port, reload=reload, log_level="info"
    )
    server = uvicorn.Server(cfg)

    def _handle_int(sig, _frame):  # noqa: D401
        server.should_exit = True

    signal.signal(signal.SIGINT, _handle_int)
    asyncio.run(server.serve())
