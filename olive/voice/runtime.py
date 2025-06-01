# olive/voice/runtime.py

from __future__ import annotations

import anyio
import atexit
import os
import signal
from typing import Optional

from prompt_toolkit.patch_stdout import patch_stdout

from olive.logger import get_logger
from olive.preferences import prefs
from olive.env import is_in_sandbox
from prompt_toolkit.application import get_app_or_none

from . import stt
from .hud import VoiceStatusHUD
from .models import VoiceStatus, DeviceInfo

logger = get_logger(__name__)


def _invalidate_pt() -> None:
    """
    Ask prompt-toolkit to repaint, thread-safely.

    • Tries the global get_app_or_none()
    • Falls back to the PromptSession instance Olive created
    • Uses .invalidate() when possible; .refresh() as legacy fallback
    """
    # 1️⃣  Preferred: whatever PT considers the “current” Application
    app = get_app_or_none()

    # 2️⃣  Fallback: the PromptSession Olive owns
    if app is None:
        try:
            from olive.prompt_ui import session  # local import to avoid cycles

            app = getattr(session, "app", None)
        except Exception:  # pragma: no cover – extremely early import edge-case
            app = None

    if not app:
        return  # Nothing to repaint yet

    try:
        if hasattr(app, "invalidate"):
            app.call_from_executor(app.invalidate)
            #app.invalidate()
        elif hasattr(app, "refresh"):  # very old PT (<3.0.36)
            app.refresh()
    except Exception:
        logger.debug("Failed to invalidate PT", exc_info=True)


class VoiceRuntime:
    """
    Spins up the high-throughput recogniser in stt.py on a background AnyIO
    task and injects each utterance into the live REPL buffer.
    """

    def __init__(self) -> None:
        self._ready = False
        self._booting = False
        self._recogniser: Optional[stt.SpeechRecognizer] = None
        self._tg: Optional[anyio.abc.TaskGroup] = None
        self._portal_cm = self._portal = None
        self._stdout_patch_cm = None

        self.hud = VoiceStatusHUD()
        self._spinner_proxy = None

    # ----------------------------------------------------------------– bootstrap
    async def _bootstrap(self) -> None:
        try:
            # ─── Guardrails ────────────────────────────────────────────────
            vs = prefs.get_section("voice", cast="obj")
            if not vs.enabled or is_in_sandbox():
                logger.info("Voice disabled or sandboxed – abort bootstrap")
                return

            # Redirect Rich / stdout through PT so nothing clobbers the prompt
            if self._stdout_patch_cm is None:
                self._stdout_patch_cm = patch_stdout(raw=True)
                self._stdout_patch_cm.__enter__()

            # ─── Env + console hand-off ────────────────────────────────────
            os.environ.setdefault("WHISPER_MODEL", vs.full_model)
            os.environ.setdefault("PARTIAL_MODEL", vs.partial_model)
            from olive.ui import console as olive_console  # noqa: WPS433

            stt.console = olive_console

            # ─── Airline-backed Rich spinner ───────────────────────────────
            from olive.prompt_ui import set_airline  # ← just added

            class _PTSpinner:
                def __enter__(self):
                    set_airline("🎙 Recording…", owner=__name__)
                    return self

                def update(self, txt):
                    set_airline(txt, owner=__name__)

                def __exit__(self, *_):
                    set_airline("", owner=__name__)

            # Monkey-patch Rich.Console.status
            import types  # noqa: WPS433

            self._spinner_proxy = _PTSpinner()
            stt.console.status = types.MethodType(
                lambda _self, *a, **kw: self._spinner_proxy, stt.console
            )

            # ─── Load models (blocking) ────────────────────────────────────
            logger.info("Voice: loading models (%s)…", os.environ["WHISPER_MODEL"])
            full = stt.load_whisper(os.environ["WHISPER_MODEL"])
            tiny = stt.load_whisper(os.environ["PARTIAL_MODEL"])
            vad = stt._load_vad()

            # ─── Deliver recognised text into the REPL buffer ──────────────
            def _on_result(text: str) -> None:
                txt = text.strip()
                if not txt:
                    return
                app = get_app_or_none()
                if not app:
                    return

                def _inject() -> None:
                    buf = app.current_buffer
                    if buf.text and not buf.text.endswith("\n"):
                        buf.insert_text("\n", move_cursor=True)
                    buf.insert_text(txt + " ", move_cursor=True)
                    _invalidate_pt()

                (
                    app.call_from_executor
                    if hasattr(app, "call_from_executor")
                    else app.loop.call_soon_threadsafe
                )(_inject)

            # ─── Spin up recogniser & workers ──────────────────────────────
            self._recogniser = stt.SpeechRecognizer(
                full, tiny, vad, on_result=_on_result
            )
            self._ready = True

            if vs.verbose:
                dev = DeviceInfo(type="stt", details={"model": vs.full_model})
                self.hud.render(VoiceStatus(active=True, latency_ms=0, device=dev))

            self._tg = anyio.create_task_group()
            await self._tg.__aenter__()
            self._tg.start_soon(self._recogniser.run)

        except Exception as exc:  # noqa: BLE001
            logger.error("Voice bootstrap failed", exc_info=True)
            if self._stdout_patch_cm is not None:
                self._stdout_patch_cm.__exit__(None, None, None)
                self._stdout_patch_cm = None
            from olive.prompt_ui import set_airline

            set_airline("")  # clear bar
            self.hud.render(
                VoiceStatus(
                    active=False,
                    latency_ms=0,
                    device=DeviceInfo(type="error", details={}),
                    error=str(exc),
                )
            )
        finally:
            self._booting = False

    # ----------------------------------------------------------------– public API
    def ensure_ready(self) -> None:
        if self._ready or is_in_sandbox():
            return

        if self._portal is None:
            self._portal_cm = anyio.from_thread.start_blocking_portal()
            self._portal = self._portal_cm.__enter__()
            atexit.register(self._portal_cm.__exit__, None, None, None)

        if self._booting:
            return
        self._booting = True
        self._portal.start_task_soon(self._bootstrap)

    # ----------------------------------------------------------------– public API
    def shutdown(self) -> None:
        """
        Tear the pipeline down *asynchronously* and return immediately.
        Safe to call multiple times (second call is a no-op).
        """
        if not (self._ready or self._booting):
            return  # already stopped / in progress
        self._ready = self._booting = False

        # 1️⃣  Close the recogniser (mic + executor threads) right away
        if self._recogniser:
            try:
                self._recogniser.close()
            except Exception:  # noqa: BLE001
                logger.debug("recogniser.close raised", exc_info=True)
            self._recogniser = None

        # 2️⃣  Ask the TaskGroup to exit – schedule, don’t block UI thread
        if self._tg and self._portal:
            try:
                self._portal.start_task_soon(self._tg.__aexit__, None, None, None)
            except Exception:
                logger.debug("TaskGroup __aexit__ scheduling failed", exc_info=True)
            self._tg = None

        # 3️⃣  Close the blocking-portal context-manager asynchronously too
        if self._portal_cm:

            def _close_cm() -> None:
                try:
                    self._portal_cm.__exit__(None, None, None)
                finally:
                    self._portal_cm = self._portal = None

            try:
                if self._portal:
                    self._portal.start_task_soon(_close_cm)
                else:  # fallback – shouldn’t happen
                    _close_cm()
            except Exception:
                logger.debug("portal_cm exit scheduling failed", exc_info=True)

        # 4️⃣  Unpatch stdout
        if self._stdout_patch_cm is not None:
            try:
                self._stdout_patch_cm.__exit__(None, None, None)
            finally:
                self._stdout_patch_cm = None


# singleton ----------------------------------------------------------------
runtime = VoiceRuntime()


def _shutdown_handler(*_) -> None:
    runtime.shutdown()


atexit.register(_shutdown_handler)
signal.signal(signal.SIGTERM, _shutdown_handler)
