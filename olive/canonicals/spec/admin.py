# cli/olive/canonicals/admin.py
import json
import shlex
from datetime import datetime
from olive.tools import tool_registry
from olive.prompt_ui import session, olive_management_command
from rich import print


USAGE = "[yellow]Usage: :spec [list|create|complete|cancel] ...[/yellow]"


@olive_management_command(":spec")
def spec_command(args: str = ""):
    """Manage feature specs: list, create, complete, cancel."""

    tokens = shlex.split(args)
    if not tokens:
        print(USAGE)
        return

    command = tokens[0].lower()

    if command == "create":
        title = (
            " ".join(tokens[1:])
            if len(tokens) > 1
            else session.prompt("📝 Feature title: ").strip()
        )
        description = f"Generated from user input at {datetime.now()}"
        payload = json.dumps(
            {"command": "create", "title": title, "description": description}
        )

    elif command == "complete":
        spec_id = (
            tokens[1] if len(tokens) > 1 else session.prompt("🆔 Spec ID: ").strip()
        )
        message = session.prompt("💬 Commit message (blank = default): ").strip()
        payload = json.dumps(
            {"command": "complete", "spec_id": spec_id, "message": message}
        )

    elif command == "cancel":
        spec_id = (
            tokens[1]
            if len(tokens) > 1
            else session.prompt("🆔 Spec ID to cancel: ").strip()
        )
        message = session.prompt("💬 Commit message (blank = default): ").strip()
        payload = json.dumps(
            {"command": "cancel", "spec_id": spec_id, "message": message}
        )

    elif command == "use":
        spec_id = (
            tokens[1] if len(tokens) > 1 else session.prompt("🆔 Spec ID: ").strip()
        )
        payload = json.dumps({"command": "use", "spec_id": spec_id})

    elif command == "list":
        payload = json.dumps({"command": "list"})

    else:
        print(f"[red]Unknown spec command: {command}[/red]")
        print(USAGE)
        return

    result = tool_registry.dispatch("spec", payload)
    print(json.dumps(result, indent=2))
