# olive/ui/__init__.py
import threading
from contextlib import contextmanager, nullcontext

from rich.console import Console
from rich.theme import Theme

# ─── Default Olive Color Scheme ─────────────────────────────────────────
# ─── TokyoNight-flavoured Olive theme ─────────────────────────────
# Reference: https://github.com/folke/tokyonight.nvim (Night style)
OLIVE_THEME = Theme(
    {
        # Brand / primary interaction
        "primary": "bold #7aa2f7",  # Blue (Tokyonight "blue")
        "secondary": "#bb9af7",  # Purple
        "success": "#9ece6a",  # Green
        "warning": "bold #e0af68",  # Yellow/Orange
        "error": "bold #f7768e",  # Red
        "info": "dim #7dcfff",  # Cyan
        "highlight": "bold #ff9e64",  # Peach highlight
        "prompt": "bold #7aa2f7",  # Same blue as primary
        # Airline / toolbar classes (new)
        "airline-bg": "#1a1b26",  # Tokyonight background
        "airline-fg": "#c0caf5",  # Light foreground text
    }
)


# Shared console instance using the olive theme
console = Console(theme=OLIVE_THEME)


# ------------------------------------------------------------------#
# Thread‑safe helper for background updates
# ------------------------------------------------------------------#
# Rich keeps an internal RLock at `console._lock`, but that’s an
# implementation detail.  We expose a tiny façade so other modules
# can do:
#     with console_lock():   # safe no‑op if lock not present
#         console.status(...) ...
@contextmanager
def console_lock():
    """
    Yield Rich’s internal lock if it exists, else a null‑context.
    Safe to use both in main and background threads.
    """
    lock: threading.RLock | None = getattr(console, "_lock", None)
    if lock:
        with lock:
            yield
    else:  # fallback for odd future Rich versions
        with nullcontext():
            yield


# ─── Helper Print Functions ─────────────────────────────────────────────
def print_primary(message: str, **kwargs) -> None:
    """Print a message in the primary brand color."""
    console.print(f"[primary]{message}[/primary]", **kwargs)


def print_secondary(message: str, **kwargs) -> None:
    """Print a message in the secondary accent color."""
    console.print(f"[secondary]{message}[/secondary]", **kwargs)


def print_info(message: str, **kwargs) -> None:
    """Print an informational message."""
    console.print(f"[info]{message}[/info]", **kwargs)


def print_success(message: str, **kwargs) -> None:
    """Print a success message."""
    console.print(f"[success]{message}[/success]", **kwargs)


def print_warning(message: str, **kwargs) -> None:
    """Print a warning message."""
    console.print(f"[warning]{message}[/warning]", **kwargs)


def print_error(message: str, **kwargs) -> None:
    """Print an error message."""
    console.print(f"[error]{message}[/error]", **kwargs)


def print_highlight(message: str, **kwargs) -> None:
    """Print a highlighted message."""
    console.print(f"[highlight]{message}[/highlight]", **kwargs)


# Expose the theme for external usage
default_theme = OLIVE_THEME
