# olive/voice/models.py
"""
Pure-data models for Olive’s voice subsystem.

Downloading of Whisper weights is handled entirely by stt.py, so this file
contains **no network logic**.  We simply expose typed settings objects
and a tiny helper for HUD/runtimes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
#  User-facing settings (mapped straight from preferences.yml)
# --------------------------------------------------------------------------- #
class VoiceSettings(BaseModel):
    enabled: bool = Field(True, description="Master kill-switch")
    verbose: bool = Field(False, description="Extra console output")

    # STT models
    partial_model: str = Field("tiny.en", description="Tiny model for partials")
    full_model: str = Field("distil-medium.en", description="Main accuracy model")

    # storage & I/O
    models_dir: str = Field("~/.olive/models/voice", description="Cache directory")
    input_device: int | None = Field(
        None, description="PortAudio device index (None → auto-detect first mic)"
    )

    # ---- legacy alias (keeps older code working) --------------------------
    @property
    def model_size(self) -> str:
        return self.full_model

    class Config:
        extra = "ignore"


# --------------------------------------------------------------------------- #
#  Runtime / HUD helpers
# --------------------------------------------------------------------------- #
class DeviceInfo(BaseModel):
    type: str
    details: Dict[str, str] = Field(default_factory=dict)


class VoiceStatus(BaseModel):
    active: bool
    latency_ms: float
    wer: Optional[float] = None
    device: DeviceInfo
    error: Optional[str] = None


# --------------------------------------------------------------------------- #
#  Stub – kept so imports elsewhere don’t break.  It only ensures the
#  models_dir exists; real downloads happen inside stt.py on demand.
# --------------------------------------------------------------------------- #
def ensure_models(*, spinner: bool = False) -> None:  # noqa: D401, ANN001
    """
    No-op placeholder.  Only creates the models_dir so that stt.py’s cache path
    is guaranteed to exist.  All weight fetching is handled automatically by
    faster-whisper when the recogniser starts.
    """
    from olive.preferences import prefs

    vs = prefs.get_section("voice", cast="obj")  # type: ignore[import-not-found]
    Path(vs.models_dir).expanduser().mkdir(parents=True, exist_ok=True)
