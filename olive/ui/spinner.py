# olive/ui/spinner.py
# olive/ui/spinner.py
from __future__ import annotations

from contextlib import contextmanager, nullcontext
from typing import Dict

from prompt_toolkit.application import get_app_or_none, run_in_terminal
from rich.console import Console
from rich.errors import LiveError

# ------------------------------------------------------------------ #
#  Config
# ------------------------------------------------------------------ #
console = Console()  # inherits Olive theme automatically

_SPINNERS: Dict[str, str] = {
    "dots": "dots",  # Rich built-ins: "dots", "line", "earth", …
}
_DEFAULT = "dots"


# ------------------------------------------------------------------ #
#  Public context manager
# ------------------------------------------------------------------ #
@contextmanager
def safe_status(
    *args,
    message: str | None = None,
    spinner: str | None = None,
):
    """
    Universal status / spinner.

    Examples
    --------
    >>> with safe_status("Building…"):
    ...     do_work()
    >>> with safe_status(message="[cyan]Thinking…[/cyan]", spinner="earth") as st:
    ...     st.update("Still thinking…")
    """
    # ---- normalise args -------------------------------------------------
    if args and message:
        raise TypeError("Give the message either positionally or by keyword, not both")
    if args:
        message = str(args[0])
    message = message or "Working…"
    spinner = _SPINNERS.get(spinner or _DEFAULT, _DEFAULT)

    # ---- branch: Prompt-Toolkit not present -----------------------------
    app = get_app_or_none()
    if app is None:
        # Nested spinners raise LiveError → degrade to a silent surrogate
        try:
            with console.status(message, spinner=spinner) as st:
                yield st
        except LiveError:

            class _NoOp:
                def update(self, *_a, **_kw): ...
                def __enter__(self):
                    return self

                def __exit__(self, *_e): ...

            with nullcontext(_NoOp()) as st:
                yield st
        return

    # ---- Prompt-Toolkit present → run Rich under run_in_terminal --------
    box: Dict[str, object] = {}

    class _NoOp:
        def update(self, *_a, **_kw): ...
        def __enter__(self):
            return self

        def __exit__(self, *_e): ...

    def _enter():
        box["obj"] = console.status(message, spinner=spinner)
        box["obj"].__enter__()

    def _exit(exc_type=None, exc=None, tb=None):
        obj = box.get("obj")
        if obj is not None and not isinstance(obj, _NoOp):
            obj.__exit__(exc_type, exc, tb)

    try:
        run_in_terminal(_enter)
    except LiveError:  # another Live already active
        box["obj"] = _NoOp()  # fall back to no-op

    try:
        yield box["obj"]
    finally:
        run_in_terminal(_exit)
