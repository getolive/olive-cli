"""
Olive Voice REPL commands
─────────────────────────
:voice-enable      – start live STT for this session
:voice-disable     – stop it
:voice-toggle      – convenience toggle
:voice-status      – show prefs + live runtime state
"""

from __future__ import annotations

import threading
from olive.prompt_ui import olive_management_command
from olive.logger import get_logger
from olive.preferences import prefs
from olive.ui import print_info, print_success, print_warning
from olive.env import is_in_sandbox
from .runtime import runtime

logger = get_logger(__name__)


# ─── utilities ─────────────────────────────────────────────────────
def _run_bg(func) -> None:
    """Fire-and-forget helper so we never block the prompt_toolkit UI thread."""
    threading.Thread(target=func, daemon=True).start()


def _in_container() -> bool:
    if is_in_sandbox():
        print_warning("Voice is disabled inside sandbox containers.")
        return True
    return False


# ─── commands ──────────────────────────────────────────────────────
@olive_management_command(":voice-enable")
def voice_enable(_args: str = ""):
    """Enable live voice transcription for this session."""
    if _in_container():
        return

    if runtime._ready:
        print_info("Voice is already enabled.")
        return

    _run_bg(runtime.ensure_ready)
    print_success("🎙 Voice pipeline starting… speak when you see the spinner.")


@olive_management_command(":voice-disable")
def voice_disable(_args: str = ""):
    """Disable live voice transcription."""
    if not (runtime._ready or runtime._booting):
        print_info("Voice is already disabled.")
        return

    _run_bg(runtime.shutdown)
    print_success("🔇 Voice pipeline stopping…")


@olive_management_command(":voice-toggle")
def voice_toggle(_args: str = ""):
    """Toggle voice on/off."""
    if runtime._ready:
        voice_disable()
    else:
        voice_enable()


@olive_management_command(":voice-status")
def voice_status(_args: str = ""):
    """Show voice prefs and runtime state."""
    from olive.ui import console

    console.print(prefs.get_section("voice"))

    state = (
        "[green]READY[/green]"
        if runtime._ready
        else "[yellow]BOOTING[/yellow]"
        if runtime._booting
        else "[red]STOPPED[/red]"
    )
    console.print(f"Runtime status: {state}")
