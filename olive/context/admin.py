# cli/olive/context/admin.py
import json
import tempfile
from pathlib import Path

from rich.tree import Tree

from olive.canonicals.spec.models import FeatureSpec
from olive.context import context
from olive.llm import LLMProvider
from olive.logger import get_logger
from olive.preferences import prefs
from olive.prompt_ui import olive_management_command
from olive.tools.spec.state import get_active_spec_id
from olive.ui import console

logger = get_logger("context-admin")

CHAT_PREVIEW_CHARS = 100


@olive_management_command(":context")
def show_context_summary():
    context.hydrate()

    mode = (
        "Abstract"
        if prefs.get("context", "abstract", "enabled", default=False)
        else "Raw"
    )
    model_name = prefs.get("llm", "model", default="gpt-4")

    system_count = len(context.state.system)
    max_files = prefs.get("context", "max_files", default=10)
    total_files = len(context.state.files)
    file_count = min(total_files, max_files) if max_files != -1 else total_files

    chat_count = len(context.state.chat)
    metadata_count = len(context.state.metadata)

    console.print("[bold underline]🧠 Olive Context Summary[/bold underline]\n")
    console.print(f"[bold]Mode:[/bold] {mode}")
    console.print(f"[bold]Model:[/bold] {model_name}")

    # Show builder mode spec if active
    spec_id = get_active_spec_id()
    if spec_id:
        try:
            spec = FeatureSpec.load(spec_id)
            console.print(f"[bold]📌 Builder Mode:[/bold] Editing feature: {spec.title}")
        except Exception:
            pass

    console.print(f"\n[bold]System Messages:[/bold] {system_count}")
    for msg in context.state.system:
        short = msg.strip().replace("\n", " ")[:CHAT_PREVIEW_CHARS]
        console.print(f" [system] {short}{'...' if len(msg) > CHAT_PREVIEW_CHARS else ''}")

    console.print(f"[bold]Chat Messages:[/bold] {chat_count}")
    for m in context.state.chat[-5:]:
        content = m.content.replace("\n", " ")[:CHAT_PREVIEW_CHARS]
        console.print(
            f" [{m.role}] {content}{'...' if len(m.content) > CHAT_PREVIEW_CHARS else ''}"
        )

    suffix = (
        "(preferences.yml: max_files = -1 → all files included)"
        if max_files == -1
        else f"(preferences.yml: max_files = {max_files})"
    )
    console.print(f"[bold]Files Included:[/bold] {file_count} {suffix}")
    console.print(f"[bold]Metadata Files:[/bold] {metadata_count}")

    # Token estimate
    try:
        from olive.llm import LLMProvider

        llm = LLMProvider()
        messages, stats = llm.build_payload(prompt="(context summary)", dry_run=True)
        percent = (stats["token_count"] / stats["max_tokens"]) * 100
        console.print(
            f"[bold]Estimated Tokens:[/bold] {stats['token_count']} / {stats['max_tokens']} ({percent:.1f}%)"
        )

    except Exception as e:
        console.print(f"[red]Token estimation failed: {e}[/red]")

    # Show files as tree
    if file_count:
        console.print("\n[bold]Files:[/bold]")
        file_tree = Tree("Project Files")
        sorted_paths = sorted(context.state.files[:file_count], key=lambda f: f.path)

        folders = {}
        for f in sorted_paths:
            path = Path(f.path)
            parent = str(path.parent)
            line_label = f"{path.name} [{len(f.lines)} lines]"
            if parent not in folders:
                folders[parent] = file_tree.add(parent)
            folders[parent].add(line_label)

        console.print(file_tree)

    if context.state.extra_files:
        console.print("\nExtra Files: ")
        for context_file in context.state.extra_files:
            console.print(f"{context_file.path} [{len(context_file.lines)} lines]")

    console.print("\n" + "-" * 60)
    console.print("\n[dim]Run :mock-ask to view full LLM payload.[/dim]")


@olive_management_command(":dump-context")
def dump_context():
    tmp = tempfile.NamedTemporaryFile(
        delete=False, suffix="_olive_context.json", mode="w", encoding="utf-8"
    )
    json.dump(context.to_dict(), tmp, indent=2)
    tmp.close()
    console.print(f"[green]✅ Context dumped to:[/green] {tmp.name}")


@olive_management_command(":messages")
def summarize_llm_payload(arg: str = None):
    """\
    Summarize and inspect details of llm interactions and payloads (:messages <id> --> detail view)
    """
    llm = LLMProvider()
    messages, stats = llm.build_payload("(payload summary)", dry_run=True)

    def clip(s, max_len=70):
        return (s[:max_len] + "..." if len(s) > max_len else s) + f" ({len(s)} chars)"

    if arg is not None and arg.strip().isdigit():
        index = int(arg.strip())
        if index < 0 or index >= len(messages):
            console.print(
                f"[red]Invalid message index {index}. Payload only has {len(messages)} messages.[/red]"
            )
            return
        msg = messages[index]
        console.print(f"\n[bold underline]📬 Message {index}[/bold underline]\n")
        console.print(f"[bold]Role:[/bold] {msg.get('role', '?')}")
        console.print("[bold]Content:[/bold]", markup=True)
        console.print(msg.get("content", "").strip(), markup=False)
        console.print(f"\n[dim]Length: {len(msg.get('content', ''))} characters[/dim]")

        # Save to file
        tmp = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=f"_olive_message_{index}.txt",
            mode="w",
            encoding="utf-8",
        )
        tmp.write(msg.get("content", ""))
        tmp.close()
        console.print(f"\n[green]✅ Message content saved to:[/green] {tmp.name}")
        return

    console.print("\n[bold underline]🧠 Olive LLM Payload Summary[/bold underline]\n")

    for i, m in enumerate(messages):
        role = m.get("role", "?")
        content = m.get("content", "").replace("\n", " ").strip()
        console.print(f"[dim]{i:>2}[/dim] | [bold]{role:<9}[/bold] | {clip(content)}")

    sent_msg_count = sum(1 for m in messages if m["role"] in ("user", "assistant"))
    retained_msg_count = len(context.state.chat)
    skipped = retained_msg_count - sent_msg_count

    console.print("\n[bold]Summary:[/bold]")
    console.print(f"[green]Messages sent to LLM:[/green] {len(messages)}")
    console.print(
        f"[cyan]User/Assistant messages in context:[/cyan] {retained_msg_count}"
    )
    console.print(
        f"[yellow]Messages skipped (not sent due to token budget):[/yellow] {max(0, skipped)}"
    )
    console.print(
        f"[blue]Estimated token usage:[/blue] {stats['token_count']} / {stats['max_tokens']} tokens"
    )
    console.print(f"[blue]Model:[/blue] {stats['model']} ({stats['provider']})")

    # Save full payload
    tmp = tempfile.NamedTemporaryFile(
        delete=False, suffix="_olive_payload.json", mode="w", encoding="utf-8"
    )
    import json

    json.dump(messages, tmp, indent=2)
    tmp.close()
    console.print(f"\n[green]✅ Full payload saved to:[/green] {tmp.name}")
