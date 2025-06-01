#!/usr/bin/env python3
"""
Olive STT v19.3
===========================================================
* **Global** spinner while Whisper models load **and** graphs warm‑up.
* **Per‑utterance** spinner that streams tiny‑model partials; closes on final text.
* Asyncio pipeline: 1 VAD producer + N full‑model workers (GPU‑bound).
* Repetition guard + decoding safety knobs.
"""

from __future__ import annotations

import concurrent.futures
import asyncio
import difflib
import os
import sys
import time
from collections import deque
from contextlib import contextmanager, redirect_stderr
from pathlib import Path
from threading import Lock
from typing import Callable, Deque, Optional, Any

import numpy as np
import torch
import ctranslate2
import sounddevice as sd
from faster_whisper import WhisperModel
from rich.console import Console
from rich.errors import LiveError

# ───────────── Config ─────────────
from distutils.util import strtobool

VERBOSE = bool(strtobool(os.getenv("VERBOSE", "False")))
FULL_MODEL_NAME = os.getenv("WHISPER_MODEL", "distil-medium.en")
PARTIAL_MODEL_NAME = os.getenv("PARTIAL_MODEL", "tiny.en")

VAD_THRESHOLD = float(os.getenv("VAD_THRESHOLD", 0.25))
SILENCE_TIMEOUT = float(os.getenv("SILENCE_TIMEOUT", 0.8))

WHISPER_MODELS_CACHE = Path(
    os.getenv("WHISPER_MODELS", "~/.cache/faster-whisper")
).expanduser()

SAMPLE_RATE = 16_000
FRAME_SIZE = 512  # 32 ms at 16 kHz
PRE_BUFFER_SEC = 5.0  # keeps 5 s of audio before speech
PARTIAL_WINDOW_SEC = 5.0  # tail size fed to tiny model
PARTIAL_INTERVAL = 0.45  # how often to fire tiny
PARTIAL_MAX_CHARS = 50
DEBOUNCE_FRAMES = 8  # ignore blips shorter than ~0.25 s
VAD_BATCH_FRAMES = 3  # call silero once per this-many frames
CONTEXT_CHARS = 2000
DEFAULT_WORKERS = 1 if ctranslate2.get_cuda_device_count() == 0 else 4
FINAL_WORKERS = int(os.getenv("WHISPER_WORKERS", DEFAULT_WORKERS))
MAX_QUEUE_SEC = 30  # audio safety buffer
CONDITION_ON_PREV = False  # transciption should be conditioned on previous
PRE_BUFFER_FRAMES = int(PRE_BUFFER_SEC * SAMPLE_RATE / FRAME_SIZE)
PARTIAL_WINDOW_FRAMES = int(PARTIAL_WINDOW_SEC * SAMPLE_RATE / FRAME_SIZE)
FRAME_QUEUE_SIZE = int(MAX_QUEUE_SEC * SAMPLE_RATE / FRAME_SIZE)

console = Console()
_status_lock = Lock()  # serialise rich status updates


# ───────── Utilities ──────────
@contextmanager
def _mute_cpp():
    """Silence noisy C/C++ back‑ends while heavy ops run."""
    if VERBOSE:
        yield
    else:
        devnull = os.open(os.devnull, os.O_WRONLY)
        old = os.dup(2)
        os.dup2(devnull, 2)
        try:
            with redirect_stderr(sys.stderr):
                yield
        finally:
            os.dup2(old, 2)
            os.close(devnull)
            os.close(old)


def _best_compute(device: str) -> str:
    types = ctranslate2.get_supported_compute_types(device)
    prefs = (
        ["int4_float16", "int8_float16", "float16", "float32"]
        if device == "cuda"
        else ["int8_float16", "int8_bfloat16", "int8_float32", "int8", "float32"]
    )
    return next((p for p in prefs if p in types), "float32")


def load_whisper(name: str) -> WhisperModel:
    device = "cuda" if ctranslate2.get_cuda_device_count() else "cpu"
    compute = _best_compute(device)
    cache = WHISPER_MODELS_CACHE
    with _mute_cpp():
        return WhisperModel(
            name,
            device=device,
            compute_type=compute,
            cpu_threads=max(4, os.cpu_count() // 2),
            download_root=str(cache),
        )


def _load_vad() -> Any:
    with _mute_cpp():
        VAD_MODEL, _ = torch.hub.load(
            "snakers4/silero-vad",
            "silero_vad",
            trust_repo=True,
            skip_validation=False,
            verbose=VERBOSE,
        )
        return VAD_MODEL


# ───────── Recognizer ──────────
class SpeechRecognizer:
    """High‑throughput mic → VAD → tiny partials (async) + full finals (async)."""

    def __init__(
        self,
        full: WhisperModel,
        tiny: WhisperModel,
        vad: Any,
        on_result: Optional[Callable[[str], None]] = None,
    ):
        self.full, self.tiny = full, tiny
        self.on_result = on_result or (lambda t: console.print(t))

        # graceful-exit plumbing
        self._shutdown = asyncio.Event()

        # ring buffers
        self._pre: Deque[np.ndarray] = deque(maxlen=PRE_BUFFER_FRAMES)
        self._tail: Deque[np.ndarray] = deque(maxlen=PARTIAL_WINDOW_FRAMES)

        # voice activation detection
        self._vad_buf: list[np.ndarray] = []
        self._last_vad_prob: float = 0.0
        self.vad = vad

        # async queues
        self.frames_q: asyncio.Queue[np.ndarray] = asyncio.Queue(FRAME_QUEUE_SIZE)
        # self.seg_q: asyncio.Queue[np.ndarray] = asyncio.Queue(maxsize=8)
        self.seg_q: asyncio.Queue[tuple[int, np.ndarray]] = asyncio.Queue(maxsize=8)

        # recording state
        self._recording: bool = False
        self._silence_since: float | None = None
        self._last_partial_ts: float = 0.0
        self._frame_count: int = 0
        self._history: str = ""
        self._prev_final: str = ""

        # per-utterance spinners held until their segment prints
        self._spinner: Optional[Any] = None
        self._spinners: dict[int, Any] = {}

        # deterministic output ordering
        self._seg_counter = 0  # id assigned when we enqueue to seg_q
        self._next_out_id = 0  # id we expect to print next
        self._pending: dict[int, str] = {}  # id → text

        self.loop: Optional[asyncio.AbstractEventLoop] = None

        # fixed-size thread pool used by *all* blocking Whisper calls
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=FINAL_WORKERS,
            thread_name_prefix="whisper",
        )

        # warm‑up both models before the mic starts (avoids first‑sentence loss)
        self._warm_up_models()

        # start mic after warm‑up
        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            blocksize=FRAME_SIZE,
            channels=1,
            dtype="float32",
            callback=self._audio_cb,
        )
        self.stream.start()

    # ───── warm‑up ─────
    def _warm_up_models(self):
        dummy = np.zeros(SAMPLE_RATE, dtype=np.float32)
        for model in (self.full, self.tiny):
            with _mute_cpp():
                model.transcribe(
                    dummy,
                    beam_size=1,
                    language="en",
                    vad_filter=False,
                    condition_on_previous_text=False,
                )

    # ───── audio callback helper
    def _enqueue_frame(self, frame: np.ndarray):
        try:
            self.frames_q.put_nowait(frame)
        except asyncio.QueueFull:
            pass

    # ───── audio callback (runs in SD thread) ─────
    def _audio_cb(self, indata, *_):
        frame = indata[:, 0].copy()
        if self.loop and self.loop.is_running():
            try:
                self.loop.call_soon_threadsafe(self._enqueue_frame, frame)

            except asyncio.QueueFull:
                pass  # drop if producer outruns consumer (rare)

    # ───── helper ─────
    @staticmethod
    def _is_repeat(a: str, b: str) -> bool:
        if not a or not b:
            return False
        ratio = difflib.SequenceMatcher(None, a, b).ratio()
        return ratio > 0.85 and len(a) > 20

    # ─── helper: run VAD on a batch stack ───
    def _vad_batch(self, frames: list[np.ndarray]) -> float:
        """Stack N frames (N×512) and return the max speech probability."""
        batch = torch.from_numpy(np.stack(frames, axis=0))
        with torch.no_grad():
            probs = self.vad(batch, SAMPLE_RATE).squeeze()  # shape (N,)
        return float(probs.max().item())

    # ───── ordered emit ─────
    async def _enqueue_final(self, seg_id: int, text: str):
        """Store text by id and flush any ready-in-order outputs."""
        if self._is_repeat(text, self._prev_final):
            spin = self._spinners.pop(seg_id, None)
            if spin:
                with _status_lock:
                    try:
                        spin.__exit__(None, None, None)
                    except LiveError:
                        pass
            return

        self._prev_final = text
        self._pending[seg_id] = text

        while self._next_out_id in self._pending:
            out_text = self._pending.pop(self._next_out_id)
            self._history = (self._history + out_text + " ")[-CONTEXT_CHARS:]

            spin = self._spinners.pop(self._next_out_id, None)
            if spin:
                with _status_lock:
                    try:
                        spin.update(f"🎙 {out_text}")
                        spin.__exit__(None, None, None)
                    except LiveError:
                        pass
            self.on_result(out_text)
            self._next_out_id += 1

    # ───── tiny partial ─────
    async def _partial_transcribe(self, audio: np.ndarray):
        segments, _ = await asyncio.to_thread(
            self.tiny.transcribe,
            audio,
            beam_size=1,
            language="en",
            vad_filter=False,
            condition_on_previous_text=False,
            no_repeat_ngram_size=3,
            log_prob_threshold=-1.0,
            compression_ratio_threshold=2.4,
            temperature=0.0,
            initial_prompt=self._history[-CONTEXT_CHARS:],
        )
        snippet = " ".join(s.text for s in segments).strip()[-PARTIAL_MAX_CHARS:]
        if snippet and self._spinner:
            with _status_lock:
                try:
                    self._spinner.update(f"🎙 {snippet}…")
                except LiveError:
                    pass

    # ───── full worker ─────
    async def _full_worker(self):
        loop = asyncio.get_running_loop()
        while True:
            seg_id = None
            try:
                seg_id, audio = await self.seg_q.get()
                use_ctx = CONDITION_ON_PREV  # global or env toggle
                prompt = self._history[-CONTEXT_CHARS:] if use_ctx else ""
                segments, _ = await loop.run_in_executor(
                    None,
                    lambda: self.full.transcribe(
                        audio,
                        beam_size=1,
                        language="en",
                        vad_filter=False,
                        condition_on_previous_text=use_ctx,
                        no_repeat_ngram_size=3,
                        log_prob_threshold=-1.0,
                        compression_ratio_threshold=2.4,
                        temperature=0.0,
                        initial_prompt=prompt,
                    ),
                )

                text = " ".join(s.text for s in segments).strip()
                if text and text[-1] not in ".?!":
                    text += "."

                # queue for ordered output
                await self._enqueue_final(seg_id, text)

            except asyncio.CancelledError:
                raise

            except Exception as _:
                console.print_exception()

            finally:
                if seg_id is not None:
                    self.seg_q.task_done()

    # ───── VAD producer ─────
    async def _vad_loop(self):
        while not self._shutdown.is_set():
            frame = await self.frames_q.get()
            now = time.monotonic()

            # populate ring buffers regardless
            self._pre.append(frame)
            if self._recording:
                self._tail.append(frame)

            # ─── batch VAD every VAD_BATCH_FRAMES duration in ms ───
            self._vad_buf.append(frame)
            if len(self._vad_buf) >= VAD_BATCH_FRAMES:
                frames = self._vad_buf
                self._vad_buf = []  # start new batch
                self._last_vad_prob = await asyncio.to_thread(self._vad_batch, frames)
            prob = self._last_vad_prob

            if prob > VAD_THRESHOLD:  # speech detected
                if not self._recording:
                    # ─── start of new utterance ───
                    self._recording = True
                    self._buffer: list[np.ndarray] = list(self._pre)
                    self._tail = deque(self._pre, maxlen=PARTIAL_WINDOW_FRAMES)
                    self._frame_count = 0
                    self._last_partial_ts = now
                    self._silence_since = None

                    # open per‑utterance spinner
                    try:
                        self._spinner = console.status("🎙 Recording…", spinner="dots")
                        self._spinner.__enter__()
                    except LiveError:
                        self._spinner = None

                # accumulate frame
                self._buffer.append(frame)
                self._frame_count += 1
                self._silence_since = None

                # schedule tiny partial every PARTIAL_INTERVAL
                if (
                    now - self._last_partial_ts >= PARTIAL_INTERVAL
                    and self._frame_count > DEBOUNCE_FRAMES
                ):
                    self._last_partial_ts = now
                    audio_tail = np.concatenate(list(self._tail))
                    if audio_tail.shape[0] < int(0.5 * SAMPLE_RATE):
                        pad = int(0.5 * SAMPLE_RATE) - audio_tail.shape[0]
                        audio_tail = np.pad(audio_tail, (0, pad))
                    asyncio.create_task(self._partial_transcribe(audio_tail))

            else:  # silence
                if self._recording:
                    if self._silence_since is None:
                        self._silence_since = now
                    elif now - self._silence_since >= SILENCE_TIMEOUT:
                        # ─── end of utterance ───
                        self._recording = False
                        segment_audio = np.concatenate(self._buffer)
                        if segment_audio.shape[0] < int(0.5 * SAMPLE_RATE):
                            pad = int(0.5 * SAMPLE_RATE) - segment_audio.shape[0]
                            segment_audio = np.pad(segment_audio, (0, pad))

                        # update spinner to "processing" while full decoders run
                        if self._spinner:
                            with _status_lock:
                                try:
                                    self._spinner.update(
                                        "Processing to improve accuracy…"
                                    )
                                except LiveError:
                                    pass

                        seg_id = self._seg_counter
                        self._seg_counter += 1
                        self._spinners[seg_id] = self._spinner
                        self._spinner = None

                        await self.seg_q.put((seg_id, segment_audio))

                        self._buffer.clear()
                        self._tail.clear()
                        self._frame_count = 0
                        self._pre.clear()

    # ───── public API ─────
    async def run(self):
        """Start VAD producer + workers; clean shutdown via TaskGroup."""
        async with asyncio.TaskGroup() as tg:
            self.loop = asyncio.get_running_loop()
            self.loop.set_default_executor(self.executor)

            tg.create_task(self._vad_loop(), name="voice_activation_detection")
            for _ in range(FINAL_WORKERS):
                tg.create_task(self._full_worker(), name="full_worker")
            try:
                await asyncio.Future()  # run forever
            except asyncio.CancelledError:
                # 1️⃣ stop VAD, 2️⃣ wait remaining GPU jobs, 3️⃣ re-raise
                self._shutdown.set()
                await self.seg_q.join()
                raise

    def close(self):
        """Stop sound stream and clean up."""
        try:
            self.stream.stop()
            time.sleep(0.05)
            if hasattr(self.stream, "abort"):
                self.stream.abort(ignore_errors=True)
        finally:
            self.stream.close()
            self.executor.shutdown(wait=False)


# ───────── entry point ─────────
async def main():
    with console.status("[cyan]Loading Whisper models & warming up…", spinner="dots"):
        try:
            full = load_whisper(FULL_MODEL_NAME)
            tiny = load_whisper(PARTIAL_MODEL_NAME)

            def _fmt(m: WhisperModel) -> str:
                """
                Return '<compute_type>@<DEVICE>' for a loaded WhisperModel.
                Works with faster-whisper ≥0.10.0 which hides these on the
                internal CT2 translator object.
                """
                # Newer faster-whisper may expose them directly one day
                if hasattr(m, "compute_type") and hasattr(m, "device"):
                    ct, dev = m.compute_type, m.device
                # Current path: grab them from the underlying CT2 model
                elif hasattr(m, "model"):
                    ct = getattr(m.model, "compute_type", "unknown")
                    dev = getattr(m.model, "device", "CPU")
                else:  # last-chance fallback
                    ct, dev = "unknown", "CPU"
                return f"{ct}@{dev.upper()}"

            vad = _load_vad()
            recognizer = SpeechRecognizer(full, tiny, vad)

        except Exception as e:
            console.print(
                f"[red]Failed to load models for speech recognition: {str(e)}"
            )
            sys.exit(-1)

    if VERBOSE:
        console.print(
            f"Loaded [bold]{FULL_MODEL_NAME}[/bold] ({_fmt(full)}) ({FINAL_WORKERS} workers) and "
            f"[bold]{PARTIAL_MODEL_NAME}[/bold] ({_fmt(tiny)}) "
            "using [bold]silero-vad[/bold] for voice activation detection."
        )

    try:
        await recognizer.run()
    except (asyncio.exceptions.CancelledError, KeyboardInterrupt, SystemExit):
        recognizer.close()
        if VERBOSE:
            console.print("\n👋 bye")


if __name__ == "__main__":
    asyncio.run(main())
