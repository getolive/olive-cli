# cli/olive/tasks/models.py
"""
Task‑related data models for Olive.

• All models are Pydantic v2 (`model_config = ConfigDict(...)`).
• `TaskStatus` is a proper Enum, so Pydantic can emit JSON‑schema.
• File writes are atomic (tmp‑file → replace) to avoid half‑written JSON.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from olive import env
from olive.logger import get_logger

logger = get_logger(__name__)

_TASKS_ROOT = env.get_dot_olive() / "run" / "tasks"
_TASKS_ROOT.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Status Enum
# ---------------------------------------------------------------------------


class TaskStatus(str, Enum):
    """Lifecycle states for a task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Task specification (immutable once dispatched)
# ---------------------------------------------------------------------------


class TaskSpec(BaseModel):
    """Defines a task’s identity and input payload."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    name: str
    input: Any | None = None
    return_id: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None

    # ---------- filesystem helpers -------------------------------------------------

    def path(self) -> Path:
        return _TASKS_ROOT / f"{self.id}.json"

    def result_path(self) -> Path:
        return _TASKS_ROOT / f"{self.return_id or self.id}.result.json"

    # ---------- persistence ---------------------------------------------------------

    def save(self) -> None:
        """Atomically persist this spec as JSON."""
        p = self.path()
        tmp = p.with_suffix(".tmp")
        tmp.write_text(self.model_dump_json(indent=2))
        tmp.replace(p)

    @classmethod
    def load(cls, path_or_id: str | Path) -> "TaskSpec":
        """
        Load a spec by filepath or bare ID.
        If given an ID, it looks for <tasks_root>/{id}.json
        """
        path = Path(path_or_id)
        if not path.exists():
            path = _TASKS_ROOT / f"{path_or_id}.json"
        return cls.model_validate_json(path.read_text())


# ---------------------------------------------------------------------------
# Task result
# ---------------------------------------------------------------------------


class TaskResult(BaseModel):
    """Captures the outcome of a task execution."""

    model_config = ConfigDict(extra="ignore")

    output: Any | None = None
    error: str | None = None
    status: TaskStatus = TaskStatus.COMPLETED

    # ---------- persistence ---------------------------------------------------------

    def save(self, spec: TaskSpec) -> None:
        """Atomically persist the result to disk."""
        p = spec.result_path()
        tmp = p.with_suffix(".tmp")
        tmp.write_text(self.model_dump_json(indent=2))
        tmp.replace(p)


# ---------------------------------------------------------------------------
# In‑memory task wrapper (ties coroutine to spec/result)
# ---------------------------------------------------------------------------


class Task(BaseModel):
    """
    Represents a running asynchronous task.

    • Executes the coroutine produced by `_coro_factory`.
    • Writes its `TaskResult` to disk on completion/failure.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    spec: TaskSpec
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[TaskResult] = None

    # private attrs (not part of the serialised model)
    _coro_factory: Callable[[], Any] = PrivateAttr()
    _task: Optional[asyncio.Task] = PrivateAttr(default=None)

    # ---------------------------------------------------------------------

    def __init__(self, spec: TaskSpec, coro_factory: Callable[[], Any]):  # noqa: D401
        super().__init__(spec=spec)
        self._coro_factory = coro_factory

    # ---------------------------------------------------------------------

    async def run(self) -> None:
        """Execute the coroutine and capture its result."""
        self.status = TaskStatus.RUNNING
        self.spec.start_time = datetime.utcnow()

        try:
            output = await self._coro_factory()
            self.status = TaskStatus.COMPLETED
            self.result = TaskResult(output=output, status=self.status)
        except Exception as exc:  # noqa: BLE001
            self.status = TaskStatus.FAILED
            self.result = TaskResult(output=None, error=str(exc), status=self.status)
        finally:
            self.spec.end_time = datetime.utcnow()
            if self.result:
                try:
                    self.result.save(self.spec)
                except Exception as e:  # noqa: BLE001
                    logger.exception(
                        f"Failed to save TaskResult for {self.spec.id}: {e}"
                    )

    # ---------------------------------------------------------------------

    def cancel(self) -> None:
        """Request cancellation of the underlying asyncio.Task, if running."""
        if self._task and not self._task.done():
            self._task.cancel()
            self.status = TaskStatus.CANCELLED
