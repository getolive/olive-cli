# olive/voice/backend.py

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol, Dict, Any

import numpy as np

from olive.logger import get_logger
from olive.preferences import prefs
from . import stt  # the new recogniser helpers

logger = get_logger(__name__)


# ───── minimal protocol (kept for test-suite compatibility) ────────────
class VoiceBackend(Protocol):
    def prewarm(self) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def process_audio(self, audio: "np.ndarray[np.float32]") -> str: ...
    @property
    def device_info(self) -> Dict[str, Any]: ...


# ───── STT backend (wraps stt.load_whisper) ─────────────────────────────
class SttBackend:
    def __init__(self):
        vs = prefs.get_section("voice", cast="obj")
        os.environ.setdefault("WHISPER_MODEL", vs.model_size)
        self.model = stt.load_whisper(os.environ["WHISPER_MODEL"])
        self._device_info: Dict[str, Any] = {
            "type": "stt",
            "model": os.environ["WHISPER_MODEL"],
        }

    # ------------------------------------------------------------------ API
    def prewarm(self) -> None:
        silent = np.zeros(stt.SAMPLE_RATE, dtype=np.float32)
        with stt._mute_cpp():  # noqa: SLF001
            _ = self.model.transcribe(silent, beam_size=1, language="en")

    def start(self) -> None: ...
    def stop(self) -> None: ...

    def process_audio(self, audio: "np.ndarray[np.float32]") -> str:
        segments, _ = self.model.transcribe(audio, beam_size=5, language="en")
        return " ".join(s.text for s in segments).strip()

    # ------------------------------------------------------------------ meta
    @property
    def device_info(self) -> Dict[str, Any]:
        return self._device_info


# ───── TTS backend (unchanged; still handy for :say) ────────────────────
class PiperCliBackend:
    def __init__(self):
        vs = prefs.get_section("voice", cast="obj")
        self.voice = vs.tts_voice
        self.bin = Path(vs.tts_binary).expanduser()
        self._device_info = {"type": "piper_cli", "voice": self.voice}

    prewarm = start = stop = lambda self: None  # noqa: E731

    def process_audio(self, text: str | bytes) -> bytes:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        cmd = [str(self.bin), "--voice", self.voice, "--output_file", tmp.name]
        subprocess.run(
            cmd, input=text if isinstance(text, bytes) else text.encode(), check=True
        )
        data = Path(tmp.name).read_bytes()
        tmp.close()
        Path(tmp.name).unlink(missing_ok=True)
        return data

    @property
    def device_info(self):
        return self._device_info


# ───── registry (always returns the new STT backend) ────────────────────
BACKENDS = {"stt": SttBackend, "piper_cli": PiperCliBackend}


def resolve_backend(_name: str | None = None) -> VoiceBackend:  # noqa: D401
    """Hard-wired: whatever the caller asks, return the STT backend."""
    return BACKENDS["stt"]()
