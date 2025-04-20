# tools/admin.py
from rich.console import Console
from rich.table import Table

from olive.preferences import prefs
from olive.prompt_ui import olive_management_command
from olive.tools import tool_registry


@olive_management_command(":tools")
def tools_summary_command():
    """Print a cleaned-up summary of Olive's tool configuration and availability."""
    console = Console()

    sandbox_enabled = prefs.is_sandbox_enabled()
    sandbox_msg = (
        "[green]🛡️ Sandbox enabled[/green]"
        if sandbox_enabled
        else "[bold red]⚠️ Sandbox disabled — tools will run on host[/bold red]"
    )
    table = Table(title="Olive Tool Access Summary", expand=False)

    table = Table(
        title=f"Olive Tool Access Summary (sandbox enabled: {prefs.is_sandbox_enabled()})",
        expand=False,
    )
    table.add_column("Tool")
    table.add_column("Status")
    table.add_column("Mgmt Commands")
    table.add_column("Reason")
    table.add_column("Description", style="dim")

    for entry in tool_registry.list():
        tool = entry.tool
        mgmt_cmds = (
            sorted(entry.management_commands.keys())
            if entry.management_commands
            else []
        )
        mgmt_cmd_str = ", ".join(mgmt_cmds) if mgmt_cmds else "–"
        table.add_row(
            tool.name,
            "✅" if entry.allowed else "❌",
            mgmt_cmd_str,
            entry.reason,
            tool.description or "",
        )

    mode = prefs.get("ai", "tools", "mode", default="blacklist")
    console.print(table)
    console.print(sandbox_msg)
    console.print(f"[bold]Tool Mode:[/bold] [green]{mode}[/green]")
    if mode == "whitelist":
        wl = prefs.get("ai", "tools", "whitelist", default=[])
        if wl:
            console.print("[bold]Whitelisted Commands:[/bold]")
            console.print("  " + ", ".join(sorted(wl)))
    elif mode == "blacklist":
        bl = prefs.get("ai", "tools", "blacklist", default=[])
        if bl:
            console.print("[bold]Blacklisted Commands:[/bold]")
            console.print("  " + ", ".join(sorted(bl)))

    console.print("[dim]Tools are manually invokable with !!toolname[/dim]")
    console.print("[dim]Configured in ~/.olive/preferences.yml[/dim]")
