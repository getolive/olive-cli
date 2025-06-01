from typing import List, Dict, Any

import sounddevice as sd
import typer
from rich.table import Table
from olive.ui import console

voice_app = typer.Typer(help="Voice-related commands")


@voice_app.command("devices")
def list_devices():
    """
    Show all PortAudio input/output devices so users can pick the right index
    for `voice.input_device` in preferences.yml.
    """
    devs: List[Dict[str, Any]] = sd.query_devices()
    hosts = sd.query_hostapis()

    table = Table(title="Audio Devices", show_header=True, header_style="bold blue")
    table.add_column("Idx", style="cyan", justify="right")
    table.add_column("Name", style="magenta")
    table.add_column("Host API", style="green")
    table.add_column("In-ch")
    table.add_column("Out-ch")

    for idx, dev in enumerate(devs):
        api_name = hosts[dev["hostapi"]]["name"]
        table.add_row(
            str(idx),
            dev["name"],
            api_name,
            str(dev["max_input_channels"]),
            str(dev["max_output_channels"]),
        )

    console.print(table)
