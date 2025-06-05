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
        "primary": "bold #7aa2f7",  # Tokyonight blue
        "secondary": "#bb9af7",  # Tokyonight purple/magenta
        "success": "#9ece6a",  # Tokyonight green
        "warning": "bold #e0af68",  # Tokyonight yellow
        "error": "bold #f7768e",  # Tokyonight red
        "info": "dim #7dcfff",  # Tokyonight cyan
        "highlight": "bold #ff9e64",  # Tokyonight orange/peach
        "prompt": "bold #7aa2f7",  # Tokyonight blue
        # Airline / toolbar classes
        "airline-bg": "#1a1b26",  # True background
        "airline-fg": "#c0caf5",  # True foreground
        # Markdown refinements
        "markdown.code": "bold #ff9e64",  # Peach for code blocks
        "markdown.code_block": "bold #ff9e64",  # Explicit for code blocks (some Rich versions)
        "markdown.h1": "bold #7aa2f7",  # Primary blue for H1
        "markdown.h2": "bold #bb9af7",  # Secondary purple for H2
        "markdown.h3": "#7dcfff",  # Cyan for H3
        "markdown.bold": "bold #c0caf5",  # Foreground bright
        "markdown.italic": "italic #bb9af7",  # Italic purple
        "markdown.block_quote": "#565f89",  # Dim comment color
        "markdown.list_item": "#c0caf5",  # Foreground
        "markdown.hr": "#3b4261",  # Border color
        "markdown.link": "underline #7aa2f7",  # Underlined blue
        "markdown.table_border": "#3b4261",  # Table border
        # Add additional keys if you want to theme, e.g. inline code, etc.
        "markdown.inline_code": "#ff9e64",
        # Fallback/foreground
        "repr.number": "#e0af68",  # Numbers in code
        "repr.str": "#9ece6a",  # Strings in code
        "repr.bool_true": "#7aa2f7",
        "repr.bool_false": "#f7768e",
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
