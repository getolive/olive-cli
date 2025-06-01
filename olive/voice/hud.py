# olive/voice/hud.py

from olive.ui import console
from olive.logger import get_logger
from olive.preferences import prefs
from .models import VoiceStatus

logger = get_logger(__name__)


class VoiceStatusHUD:
    """
    Status output is helpful while debugging, but it clutters the screen during
    normal use.  We therefore only render it when `voice.verbose` is **true**.
    """

    def render(self, status: VoiceStatus) -> None:
        vs = prefs.get_section("voice", cast="obj")
        if not getattr(vs, "verbose", False):
            return  # stay quiet by default

        parts = ["🫒 active" if status.active else "[dim]🫒 idle[/dim]"]
        if status.device:
            desc = ", ".join(f"{k}={v}" for k, v in status.device.details.items())
            parts.append(desc)
        if status.error:
            parts.append(f"[red]{status.error}[/red]")

        console.print(" • ".join(parts), highlight=False, overflow="crop")
