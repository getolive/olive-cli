# cli/olive/canonicals/admin.py
from olive.prompt_ui import olive_management_command
from olive.canonicals import canonicals_registry
from rich.table import Table
from rich import print

@olive_management_command(":canonicals")
def canonicals_summary_command():
    """Show discovered canonicals and their install status."""
    canonicals = canonicals_registry.list()

    if not canonicals:
        print("[yellow]⚠️ No canonicals discovered.[/yellow]")
        return

    table = Table(title="📦 Canonicals", header_style="bold blue")
    table.add_column("", style="bold")
    table.add_column("Name", style="bold")
    table.add_column("Status")
    table.add_column("Message", style="dim")

    for name in sorted(canonicals.keys()):
        canonical = canonicals[name]
        icon = "✅" if canonical.installed else "❌"
        status = "Installed" if canonical.installed else "Missing"
        table.add_row(icon, name, status, canonical.message)

    print(table)
