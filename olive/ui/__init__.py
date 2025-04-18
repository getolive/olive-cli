# olive/ui/__init__.py
import threading
from contextlib import contextmanager, nullcontext
from rich.console import Console
from rich.theme import Theme

# ─── Default Olive Color Scheme ─────────────────────────────────────────
# A palette centered on olive greens, with complementary accents.
OLIVE_THEME = Theme(
    {
        # Primary brand color
        "primary": "bold #556B2F",  # Dark Olive Green
        # Secondary accent
        "secondary": "#6B8E23",  # Olive Drab
        # Success / positive feedback
        "success": "#9ACD32",  # Yellow Green
        # Warnings
        "warning": "bold #FFA500",  # Orange
        # Errors
        "error": "bold #8B0000",  # Dark Red
        # Informational / less prominent
        "info": "dim #778899",  # Light Slate Gray
        # Highlights / calls to action
        "highlight": "bold magenta",
        # Prompt styling
        "prompt": "bold #6B8E23",  # Olive Drab Bold
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
