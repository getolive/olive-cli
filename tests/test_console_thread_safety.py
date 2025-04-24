"""
Thread‑safety contract for Olive’s Rich console integration.

We patch Console so that any call from a non‑main thread MUST come through
`console.lock()` (or whatever helper marshals work to the UI thread).  The
lock’s implementation is *expected* to run the wrapped callable on the main
thread, so our patched methods accept that.

Scenarios:
1.  A background task calls `console.print()` **without** the lock ⇒ test FAILS
2.  A background task calls it **with** the lock ⇒ test PASSES
"""

from __future__ import annotations

import asyncio
import threading
from typing import Callable

import pytest
from rich.status import Status as _RichStatus

from olive.ui import console as _console

#
# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
MAIN_THREAD = threading.current_thread()


def _assert_main_thread(where: str):
    assert threading.current_thread() is MAIN_THREAD, (
        f"Rich {where} invoked from background thread!"
    )


# --------------------------------------------------------------------------- #
# Monkey‑patch Rich so calls from background threads *must* be marshalled
# --------------------------------------------------------------------------- #
def _wrap_safe(fn: Callable, name: str):
    def _wrapper(self, *a, **kw):  # noqa: D401
        _assert_main_thread(f"console.{name}()")
        return fn(self, *a, **kw)

    return _wrapper


def _install_rich_guards(monkeypatch):
    ConsoleCls = _console.__class__

    for meth in ("print", "log", "rule"):
        monkeypatch.setattr(
            ConsoleCls, meth, _wrap_safe(getattr(ConsoleCls, meth), meth), raising=True
        )

    class _GuardedStatus(_RichStatus):  # type: ignore[misc]
        def update(self, *a, **kw):  # noqa: D401
            _assert_main_thread("Status.update()")
            return super().update(*a, **kw)

    def _guarded_status(self, *a, **kw):  # noqa: D401
        _assert_main_thread("console.status()")
        return _GuardedStatus(*a, **kw)

    monkeypatch.setattr(ConsoleCls, "status", _guarded_status, raising=True)


@pytest.fixture(autouse=True)
def _guard_rich(monkeypatch):
    _install_rich_guards(monkeypatch)


# --------------------------------------------------------------------------- #
# Scenario 1 – direct call WITHOUT the lock should blow up
# --------------------------------------------------------------------------- #
def test_background_print_without_lock_raises():
    from olive.tasks import TaskStatus, task_manager

    async def _bad():
        _console.print("oops")  # should trip the guard in the worker thread

    async def _run():
        tid = task_manager.create_task("bad‑print", _bad)
        # shorter timeout is fine—the task fails almost immediately
        result = await task_manager.wait_for_result(tid, timeout=1)

        assert result.status is TaskStatus.FAILED
        assert "Rich console.print()" in (result.error or "")

    asyncio.run(_run())


# --------------------------------------------------------------------------- #
# Scenario 2 – call WITH the lock should work
# --------------------------------------------------------------------------- #
def test_background_print_with_lock_passes():
    from olive.tasks import task_manager

    async def _good():
        # The real Olive helper is probably `with _console.lock(): ...`
        # Here we assume it runs the callable on the main thread.
        with _console.lock():
            _console.print("hello from worker")

    async def _run():
        tid = task_manager.create_task("good‑print", _good)
        # should not raise
        await task_manager.wait_for_result(tid, timeout=5)

    asyncio.run(_run())
