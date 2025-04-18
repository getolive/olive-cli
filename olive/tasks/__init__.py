# cli/olive/tasks/__init__.py
"""High‑reliability cross‑platform task manager for Olive.

Key features
────────────
•  Bounded concurrency (defaults to cpu‑count).
•  Lifecycle hooks (create / start / finish / fail / cancel).
•  Automatic JSON persistence of every task’s spec & result.
•  Background event‑loop handled with asyncio.Runner (3.11+).
•  Structured logging of task‑id, name, status.
•  Graceful Windows fallback where POSIX signals are missing.

⚠️  Implementation note:
    asyncio.Runner exposes only `.run()`, `.shutdown()`, and `.get_loop()`.
    Timer / thread‑safe calls must go through `loop = runner.get_loop()`.
"""

from __future__ import annotations

import asyncio
import contextvars
import os
import signal
import threading
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from olive.env import get_olive_base_path
from olive.logger import get_logger
from olive.tasks.models import Task, TaskResult, TaskSpec, TaskStatus

logger = get_logger(__name__)
OLIVE_TASK_DIR = get_olive_base_path() / "run" / "tasks"
OLIVE_TASK_DIR.mkdir(parents=True, exist_ok=True)

# ────────────────────────────────────────────────────────────────────────────────
# Hook system
# ────────────────────────────────────────────────────────────────────────────────

Hook = Callable[[Task], None]


class _HookRegistry:
    _events: Dict[str, List[Hook]] = {
        "create": [],
        "start": [],
        "finish": [],
        "fail": [],
        "cancel": [],
    }

    @classmethod
    def register(cls, event: str, fn: Hook) -> None:
        if event not in cls._events:
            raise ValueError(f"Unknown hook event: {event}")
        cls._events[event].append(fn)

    @classmethod
    def dispatch(cls, event: str, task: Task) -> None:
        for fn in cls._events.get(event, []):
            try:
                fn(task)
            except Exception:  # noqa: BLE001
                logger.exception("Hook %s failed for task %s", event, task.spec.id)


# ────────────────────────────────────────────────────────────────────────────────
# Task manager
# ────────────────────────────────────────────────────────────────────────────────


class TaskManager:
    """Manages the async lifecycle of all Olive tasks."""

    # ------------------------------------------------------------------ #

    def __init__(self, max_concurrency: int | None = None) -> None:
        self.max_concurrency = max_concurrency or (os.cpu_count() or 4)
        self._sema = asyncio.Semaphore(self.max_concurrency)

        self.tasks: Dict[str, Task] = {}
        self._result_events: Dict[str, asyncio.Event] = {}

        self._runner: Optional[asyncio.Runner] = None          # background Runner
        self._runner_thread: Optional[threading.Thread] = None
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        self._cancelled = contextvars.ContextVar("olive_task_mgr_cancelled", default=False)

        self.initialize()  # spin up immediately

    # ------------------------------------------------------------------ #
    # Initialization
    # ------------------------------------------------------------------ #

    def initialize(self) -> None:
        if self._runner is not None:  # already running
            return

        self._setup_signal_handlers()

        def _run_background() -> None:
            with asyncio.Runner() as runner:
                self._runner = runner
                loop = runner.get_loop()
                loop.set_debug(os.getenv("OLIVE_DEBUG_TASKS", "0") == "1")

                stop_event = asyncio.Event()

                async def _monitor() -> None:
                    """Wake up every 0.5 s; stop when cancelled flag is set."""
                    while not self._cancelled.get():
                        await asyncio.sleep(0.5)
                    stop_event.set()

                loop.create_task(_monitor())
                runner.run(stop_event.wait())

        self._runner_thread = threading.Thread(
            target=_run_background, name="OliveTaskLoop", daemon=True
        )
        self._runner_thread.start()
        logger.debug(
            "[TaskManager] Background asyncio.Runner started (max=%s)", self.max_concurrency
        )

    # ------------------------------------------------------------------ #
    # Task creation & waiting
    # ------------------------------------------------------------------ #

    def create_task(
        self,
        name: str,
        coro_factory: Callable[[], Any],
        *,
        input: Any | None = None,  # noqa: A002 (shadow built‑in)
    ) -> str:
        """Register and schedule a new task; returns its ID."""
        # Capture caller loop on first invocation
        if self._main_loop is None:
            try:
                self._main_loop = asyncio.get_running_loop()
            except RuntimeError as exc:
                raise RuntimeError(
                    "TaskManager.create_task() must be called inside an event loop"
                ) from exc

        spec = TaskSpec(name=name, input=input)
        spec.start_time = datetime.utcnow()
        spec.save()  # persist spec immediately

        task = Task(spec, coro_factory)
        self.tasks[spec.id] = task
        _HookRegistry.dispatch("create", task)

        # Event for callers waiting on result
        waiter_event = asyncio.Event()
        self._result_events[spec.id] = waiter_event

        async def _run_wrapper() -> None:
            async with self._sema:
                _HookRegistry.dispatch("start", task)
                try:
                    await task.run()
                    _HookRegistry.dispatch("finish", task)
                except asyncio.CancelledError:
                    task.status = TaskStatus.CANCELLED
                    _HookRegistry.dispatch("cancel", task)
                    raise
                except Exception as exc:  # noqa: BLE001
                    task.status = TaskStatus.FAILED
                    task.result = TaskResult(output=None, error=str(exc), status=task.status)
                    _HookRegistry.dispatch("fail", task)
                finally:
                    task.spec.end_time = datetime.utcnow()
                    task.spec.save()
                    if task.result:
                        task.result.save(task.spec)
                    if self._main_loop and not self._main_loop.is_closed():
                        self._main_loop.call_soon_threadsafe(waiter_event.set)

        # ---------- schedule on background loop ------------------------ #
        loop = self._runner.get_loop()  # type: ignore[union-attr]
        loop.call_soon_threadsafe(lambda: loop.create_task(_run_wrapper()))

        return spec.id

    # ------------------------------------------------------------------ #

    async def wait_for_result(
        self, task_id: str, timeout: float | None = None
    ) -> Optional[TaskResult]:
        """Await a task’s completion and receive its TaskResult (or None)."""
        ev = self._result_events.get(task_id)
        if not ev:
            logger.warning("[TaskManager] Unknown task id: %s", task_id)
            return None
        try:
            await asyncio.wait_for(ev.wait(), timeout)
        except asyncio.TimeoutError:
            logger.warning("[TaskManager] Timeout waiting for %s", task_id)
            return None
        task = self.tasks.get(task_id)
        return task.result if task else None

    # ------------------------------------------------------------------ #
    # Cancellation helpers
    # ------------------------------------------------------------------ #

    def cancel_task(self, task_id: str) -> None:
        if task := self.tasks.get(task_id):
            task.cancel()

    def cancel_all(self) -> None:
        for task in list(self.tasks.values()):
            task.cancel()

    # ------------------------------------------------------------------ #
    # Signal handling
    # ------------------------------------------------------------------ #

    def _setup_signal_handlers(self) -> None:
        def _handle(_sig, _frame):  # noqa: D401, ANN001
            logger.info("[TaskManager] Termination signal received – stopping loop")
            self._cancelled.set(True)
            self.cancel_all()

        for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
            if sig is None:
                continue
            try:
                signal.signal(sig, _handle)  # type: ignore[arg-type]
            except (ValueError, OSError):
                # Signals unavailable on Windows or inside threads
                pass

    # ------------------------------------------------------------------ #
    # Hook registration facade
    # ------------------------------------------------------------------ #

    def on(self, event: str, fn: Hook) -> None:
        _HookRegistry.register(event, fn)

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #

    def list_tasks(self) -> Dict[str, Dict[str, Any]]:  # noqa: C901 (heuristic only)
        out: Dict[str, Dict[str, Any]] = {}
        for tid, task in self.tasks.items():
            spec = task.spec
            duration: Optional[float] = None
            if spec.start_time and spec.end_time:
                duration = (spec.end_time - spec.start_time).total_seconds()

            summary: Optional[str] = None
            if task.result:
                if task.result.error:
                    summary = f"[error] {task.result.error}"
                elif isinstance(task.result.output, str):
                    summary = task.result.output[:80]
                else:
                    summary = str(task.result.output)[:80]

            out[tid] = {
                "name": spec.name,
                "status": task.status,
                "input": spec.input,
                "start": spec.start_time.isoformat() if spec.start_time else None,
                "end": spec.end_time.isoformat() if spec.end_time else None,
                "duration": f"{duration:.2f}s" if duration else None,
                "result": summary or "[no output]",
            }
        return out

    def get_task(self, task_id: str) -> Optional["Task"]:
        """Return the in-memory Task object by id, or None."""
        return self.tasks.get(task_id)

# ────────────────────────────────────────────────────────────────────────────────
# Public singleton
# ────────────────────────────────────────────────────────────────────────────────

task_manager = TaskManager()
