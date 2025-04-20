# olive/tasks/watcher.py
"""
Process‑wide watchdog manager for Olive.

Usage:

    from olive.tasks.watcher import await_file

    data_ready = await await_file(result_path, timeout=15)
    if not data_ready:
        raise TimeoutError("Result never arrived")

The module hides all watchdog details; callers just await a file.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Dict, List

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# ────────────────────────────────────────────────────────────────────────
# Internals
# ────────────────────────────────────────────────────────────────────────

_OBSERVER: Observer | None = None  # the singleton
_DIR_HANDLERS: Dict[Path, "DirectoryHandler"] = {}  # dir → handler


def _get_observer() -> Observer:
    global _OBSERVER
    if _OBSERVER is None:
        # Pick best backend automatically (FSEvents on macOS, etc.)
        _OBSERVER = Observer()
        _OBSERVER.start()
    return _OBSERVER


class DirectoryHandler(FileSystemEventHandler):
    """
    One handler per watched directory.

    Maintains a mapping {target_path: [asyncio.Event, ...]}.
    When a file is created, sets every waiter registered on that path.
    """

    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._waiters: Dict[Path, List[asyncio.Event]] = {}

    # watchdog callback
    def on_created(self, event):  # type: ignore[override]
        created = Path(event.src_path)
        events = self._waiters.pop(created, [])
        for evt in events:
            evt.set()

        # Auto‑prune empty handler
        if not self._waiters:
            _unschedule_directory(self._dir)

    # waiter management --------------------------------------------------
    def add_waiter(self, target: Path, evt: asyncio.Event) -> None:
        self._waiters.setdefault(target, []).append(evt)


def _schedule_directory(directory: Path) -> DirectoryHandler:
    """
    Ensure *directory* is being watched; return its DirectoryHandler.
    """
    directory = directory.resolve()
    if handler := _DIR_HANDLERS.get(directory):
        return handler

    handler = DirectoryHandler(directory)
    _DIR_HANDLERS[directory] = handler
    _get_observer().schedule(handler, str(directory), recursive=False)
    return handler


def _unschedule_directory(directory: Path) -> None:
    """
    Remove watch if no more waiters.
    """
    directory = directory.resolve()
    handler = _DIR_HANDLERS.pop(directory, None)
    if handler:
        _get_observer().unschedule(handler)


# ────────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────────
async def await_file(path: Path, timeout: float | None = None) -> bool:
    """
    Async‑block until *path* exists or *timeout* seconds elapse.
    Returns True if the file appeared, False on timeout.
    """
    path = path.resolve()
    if path.exists():
        return True

    evt = asyncio.Event()
    handler = _schedule_directory(path.parent)
    handler.add_waiter(path, evt)

    try:
        return await asyncio.wait_for(evt.wait(), timeout)  # True on success
    except asyncio.TimeoutError:
        # Unregister waiter on timeout
        handler._waiters[path].remove(evt)
        if not handler._waiters[path]:
            del handler._waiters[path]
            if not handler._waiters:
                _unschedule_directory(path.parent)
        return False


def wait_file(path: Path, timeout: float | None = None) -> bool:
    """
    Synchronous wrapper around await_file().
    Suitable for threads / non‑async code.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Already in an event loop → run asynchronous helper synchronously.
        return asyncio.run_coroutine_threadsafe(
            await_file(path, timeout), loop
        ).result()
    else:
        return asyncio.run(await_file(path, timeout))


def shutdown() -> None:
    """
    Stop the singleton observer. Call this in `atexit` or test teardown.
    """
    global _OBSERVER
    if _OBSERVER:
        _OBSERVER.stop()
        _OBSERVER.join()
        _OBSERVER = None
        _DIR_HANDLERS.clear()
