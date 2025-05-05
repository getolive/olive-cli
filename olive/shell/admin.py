from olive.session import _INTERRUPTED

import json
import subprocess
import sys
import tempfile
import time
from shutil import which

from rich.table import Table

from olive.context import context
from olive import env
from olive.llm import LLMProvider
from olive.logger import get_logger, get_current_log_file
from olive.prompt_ui import (
    get_management_commands,
    olive_management_command,
    olive_prompt,
    session,
)
from olive.ui import (
    console,
    print_highlight,
    print_info,
    print_secondary,
    print_success,
    print_warning,
)

logger = get_logger(__name__)
llm = LLMProvider()


@olive_management_command(":root")
def print_project_root():
    """Print the Olive project root directory."""
    root = env.get_project_root()
    print_secondary(f"olive project root: {root}")


@olive_management_command(":exit")
def perform_graceful_exit():
    """Perform all Olive shell cleanup and exit the process."""
    logger.info("User exited Olive Shell.")
    # Place for future cleanup hooks, flushes, etc.
    import sys
    sys.exit(0)

@olive_management_command(":exit")
def exit_command():
    """Exit the Olive shell."""
    perform_graceful_exit()


@olive_management_command(":help")
def help_command():
    """Print available Olive management commands."""
    print_secondary("\nAvailable Olive Commands:\n")
    for name, func in get_management_commands().items():
        doc = func.__doc__ or "(no description)"
        print_secondary(f"{name:<15} {doc.strip()}")


@olive_management_command(":logs")
def logs_command():
    """Open or display the current session log."""
    log_path = get_current_log_file()
    pager = "less" if which("less") else ("more" if which("more") else None)

    if pager:
        subprocess.run([pager, str(log_path)])
    else:
        print_info(f"📄 Log file: {log_path}")
        print_warning("No pager found. Showing contents below:\n")
        console.print(log_path.read_text())


@olive_management_command(":reset")
def reset_state_command():
    """Reset logs and context state, clearing active.json and rotating log."""
    from olive.logger import force_log_rotation

    context.reset()
    rotated = force_log_rotation()

    print_warning("🧹 Olive context has been reset.")
    if rotated:
        print_success("🔄 Log rotated and fresh olive_session.log started.")
    else:
        print_warning("⚠️ Log rotation could not be performed.")
    print_info("System prompt retained, but chat and file context are now empty.")


@olive_management_command(":mock-ask")
async def mock_ask_command():
    """Simulate an LLM request and display prompt statistics."""
    prompt = await session.prompt_async(olive_prompt)
    messages, stats = llm.mock_ask(prompt)

    print_highlight("📊 Prompt Stats")
    print_info(f"• LLM: {stats['provider']} @ {stats['provider_base_url']}")
    print_info(f"• Model: {stats['model']}")
    console.print(
        f"• Estimated tokens: [warning]{stats['token_count']}[/warning] / {stats['max_tokens']}"
    )
    print_info(f"• Files injected: {len(stats['files'])}")
    for f in stats["files"]:
        console.print(f"  - {f['path']}")

    print_info("Use :reset-cache to clear cache and make files eligible for resending.")
    print_highlight("📤 Full payload (not actually sent):")

    tmp_file = tempfile.NamedTemporaryFile(
        delete=False, suffix="_last_mock.json", mode="w", encoding="utf-8"
    )
    json.dump(messages, tmp_file, indent=2)
    tmp_file.close()
    print_success(f"Mock payload written to: {tmp_file.name}")

    context.hydrate()
    tmp_context = tempfile.NamedTemporaryFile(
        delete=False, suffix="_hydrated_context.json", mode="w", encoding="utf-8"
    )
    json.dump(context.to_dict(), tmp_context, indent=2)
    tmp_context.close()
    print_info(f"Hydrated context written to: {tmp_context.name}")


@olive_management_command(":profile")
def profile_command():
    """Display performance profile of Olive context operations."""
    table = Table(title="Olive Context Performance Profile")
    steps = []

    start = time.perf_counter()
    _ = context._discover_files()
    steps.append(("discover_files", time.perf_counter() - start))

    start = time.perf_counter()
    _ = context._build_context_payload()
    steps.append(("build_context_payload", time.perf_counter() - start))

    start = time.perf_counter()
    context.hydrate()
    steps.append(("hydrate (uncached)", time.perf_counter() - start))

    start = time.perf_counter()
    llm_inst = LLMProvider()
    llm_inst.build_payload(prompt="(profiling token estimation)")
    steps.append(("build_payload + token estimation", time.perf_counter() - start))

    table.add_column("Step")
    table.add_column("Time (ms)", justify="right")
    for label, duration in steps:
        table.add_row(label, f"{duration * 1000:.2f}")
    console.print(table)

@olive_management_command(":resume")
def resume_command():
    """Resume paused agent/autonomous work after Ctrl+C."""
    if _INTERRUPTED.is_set():
        _INTERRUPTED.clear()
        print("[Olive] Resuming agent recursion after interrupt.")
    else:
        print("[Olive] Nothing to resume; agent not paused.")
