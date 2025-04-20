"""
Global pytest fixtures for Olive.

Stops the background TaskManager runner so pytest terminates cleanly.
"""

from __future__ import annotations

import pytest

from olive.tasks import task_manager


@pytest.fixture(scope="session", autouse=True)
def _shutdown_task_manager():
    """
    Tell Olive’s background runner to exit and wait for its thread.

    We deliberately *do not* poke at the event‑loop from the main thread.
    The `asyncio.Runner` used inside Olive handles cancellation and loop
    shutdown when the thread function returns.
    """
    yield  # ── run all tests first ───────────────────────

    # 1 – signal the monitor loop to break out of its poll‑loop
    task_manager._cancelled.set(True)

    # 2 – wait for the runner thread to finish (graceful timeout)
    thread = task_manager._runner_thread
    if thread is not None:
        thread.join(timeout=1.0)
