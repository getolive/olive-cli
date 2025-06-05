# cli/olive/tasks/admin.py
import json
from datetime import datetime
from pathlib import Path

from rich.markdown import Markdown
from rich.table import Table

from olive.prompt_ui import olive_management_command
from olive.ui import console, print_error, print_warning


def get_task_manager_lazy():
    """lazy load the task manager to hackishly avoid reworking imports."""
    from olive.tasks import task_manager

    return task_manager


@olive_management_command(":tasks")
def tasks_list_command(arg: str = None):
    """\
    List recent Olive tasks. (:tasks --all --> show all known tasks)
    """
    arg = (arg or "").strip()
    show_all = arg == "--all"
    single_task_partial = arg if arg and not show_all else None

    tasks = get_task_manager_lazy().list_tasks()
    if not tasks:
        print_warning("[dim]No tasks found.[/dim]")
        return

    sorted_tasks = sorted(
        tasks.items(), key=lambda item: item[1].get("start") or "", reverse=True
    )

    if single_task_partial:
        matches = [
            tid for tid, _ in sorted_tasks if tid.startswith(single_task_partial)
        ]
        if not matches or len(matches) <= 0:
            print_error(f"No match found for task id partial {single_task_partial}")
            return
        elif len(matches) > 1:
            print_warning(
                f"Multiple matches for '{single_task_partial}': {', '.join(matches)}. Showing first."
            )

        task_get_command(matches[0], show_only_rendered_result=True)
        return

    if not show_all:
        sorted_tasks = sorted_tasks[:10]

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim", overflow="fold")
    table.add_column("Name")
    table.add_column("Input")
    table.add_column("Status")
    table.add_column("Started")
    table.add_column("Duration")
    table.add_column("Result (truncated)")

    for task_id, data in sorted_tasks:
        status = data.get("status", "?")
        name = data.get("name", "")
        input = data.get("input", "")
        start = data.get("start") or ""
        duration = data.get("duration") or ""
        result = data.get("result") or ""
        color = (
            "green"
            if status == "running"
            else (
                "red"
                if status == "failed"
                else "yellow"
                if status == "pending"
                else "dim"
            )
        )
        start_human = (
            datetime.fromisoformat(start).strftime("%Y-%m-%d %H:%M:%S") if start else ""
        )
        table.add_row(
            task_id,
            name,
            input,
            f"[{color}]{status}[/{color}]",
            start_human,
            duration,
            result,
        )

    console.print(table)


@olive_management_command(":task-get")
def task_get_command(task_id: str = None, show_only_rendered_result=False):
    """\
    Show the full in-memory task spec + result. (:task-get <task_id> --> task_id details)
    """
    if not task_id:
        print_warning("Usage: :task-get <task_id>")
        return

    task = get_task_manager_lazy().get_task(task_id)
    if not task:
        print_error(f"Task not found: {task_id}")
        return

    if show_only_rendered_result:
        from olive.shell.utils import _render_tool_result

        _render_tool_result(task.result)
    else:
        # ✅ Handles all serialization cases safely
        console.print_json(data=json.loads(task.json()))
        # print_json(data=<dict>)   # for structured data
        # print_json(json=<str>)    # for raw JSON string


@olive_management_command(":task-result")
def task_result_command(task_id: str = None):
    """\
    Show the raw result file for a task from disk (:task-result <task_id> --> details of run)
    """
    if not task_id:
        print_warning("Usage: :task-result <task_id>")
        return

    result_path = Path(f".olive/run/tasks/{task_id}.result.json")
    if not result_path.exists():
        print_error(f"Result not found: {result_path}")
        return

    try:
        result = json.loads(result_path.read_text())
        console.print_json(data=result)
    except Exception as e:
        print_error(f"Failed to read result: {e}")


@olive_management_command(":task-run")
def task_run_command(task_path: str = None):
    """\
    Execute a saved task file from disk. (:task-run .olive/run/tasks/<task_id>.json --> execute this task)
    """
    if not task_path:
        print_warning("Usage: :task-run <path_to_task.json>")
        return

    try:
        from olive.tasks.runner import run_task_from_file

        run_task_from_file(task_path)
    except Exception as e:
        print_error(f"Failed to run task: {e}")


@olive_management_command(":task-help")
def task_help_command():
    """Show help for task-related commands."""
    help_text = """\
# 🧩 Task Management Commands

- `:tasks` — Show recent tasks
- `:tasks --all` — Show full task list
- `:task-get <task_id>` — View full task spec and result from memory
- `:task-result <task_id>` — View result file from disk (e.g. sandboxed task)
- `:task-run <task_file.json>` — Run a task file manually
- `:task-help` — Show this help menu
"""
    console.print(Markdown(help_text))
