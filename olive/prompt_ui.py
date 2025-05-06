# cli/olive/prompt_ui.py
"""
prompt_ui.py manages the host shell interactions with Olive including
 - registering global :commands
 - maintaining the global session
 - utilizing the preferred prompt symbol and style
 - enabling inline/shell completion
 - wiring/handling of bindings like enter or escape
"""

import functools
import glob
import time
import inspect
import shutil
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion, PathCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.document import Document
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

from olive.logger import get_logger
from olive.preferences import prefs
from olive.ui import OLIVE_THEME, print_error, print_info

logger = get_logger(__name__)

# ─── Prompt Styling ────────────────────────────────────────────────

# Extract the 'prompt' style string from our shared OLIVE_THEME
_prompt_style = str(OLIVE_THEME.styles["prompt"])
style = Style.from_dict({"prompt": _prompt_style})

prompt_symbol = prefs.get("ui", "prompt", default="🫒")
olive_prompt = HTML(f"<prompt>{prompt_symbol} </prompt>")

# ─── Command Registry ──────────────────────────────────────────────

_command_lookup: dict[str, callable] = {}


def get_management_commands() -> dict[str, callable]:
    return _command_lookup


def register_commands(cmds: dict[str, callable]):
    _command_lookup.update(cmds)


def safe_command(fn):
    """
    Wrap a shell command handler (sync or async) to catch exceptions,
    log them, and display a styled error message via olive.ui.error().
    """
    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except Exception as e:
                logger.exception(f"Error in command '{fn.__name__}'")
                print_error(f"Command '{fn.__name__}' failed: {e}")

        return async_wrapper
    else:

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                logger.exception(f"Error in command '{fn.__name__}'")
                print_error(f"Command '{fn.__name__}' failed: {e}")

        return sync_wrapper


def olive_management_command(name: str):
    """
    Register a shell‑management command under `name`, and
    automatically wrap it in @safe_command for consistent error handling.
    """

    def decorator(fn):
        wrapped = safe_command(fn)
        wrapped._olive_is_shell_command = True
        wrapped._olive_command_name = name
        _command_lookup[name] = wrapped
        return wrapped

    return decorator


# ─── Completion ────────────────────────────────────────────────────

COMMON_CMDS = [
    "cat",
    "ls",
    "grep",
    "less",
    "echo",
    "head",
    "tail",
    "pwd",
    "touch",
    "cp",
    "mv",
]


def get_available_shell_commands() -> list[str]:
    return [cmd for cmd in COMMON_CMDS if shutil.which(cmd)]


class OliveCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.strip()

        # :command completion
        if text.startswith(":"):
            for cmd in _command_lookup:
                if cmd.startswith(text):
                    yield Completion(cmd[len(text) :], start_position=0, display=cmd)

        # ! shell command or path completion
        elif text.startswith("!"):
            parts = text[1:].split(maxsplit=1)
            if not parts:
                return  # just "!", no partial

            if len(parts) == 1:
                partial = parts[0]
                for cmd in get_available_shell_commands():
                    if cmd.startswith(partial):
                        yield Completion(cmd, start_position=-len(partial))
            else:
                _, path_start = parts
                for match in glob.glob(path_start + "*"):
                    display = match + ("/" if Path(match).is_dir() else "")
                    yield Completion(
                        match, start_position=-len(path_start), display=display
                    )

        # @ prefix (adding files to context)
        elif text.startswith("@"):
            completer = PathCompleter(expanduser=True)
            subtext = text[1:].lstrip()
            doc = Document(subtext, cursor_position=len(subtext))
            yield from completer.get_completions(doc, complete_event)


# ─── Key Bindings ──────────────────────────────────────────────────

bindings = KeyBindings()


_last_ctrl_c_time = [0]
_ctrlc_hint_active = [False]


@bindings.add("c-c")
def handle_ctrl_c(event):
    """
    Double Ctrl+C to exit. Single Ctrl+C clears buffer (if not empty) or prompts to double-tap.
    """
    try:
        now = time.time()
        buf = event.app.current_buffer
        app = event.app
        logger.debug(
            f"[handle_ctrl_c] called: now={now}, last={_last_ctrl_c_time[0]}, buf.text={repr(buf.text)}"
        )

        if buf.text:
            buf.reset()
            try:
                app.layout.reset()
            except Exception:
                pass
            app.invalidate()
            if hasattr(app, "_redraw"):
                try:
                    app._redraw()
                except Exception:
                    pass
            # Cleared prompt input. (Press Ctrl+C again quickly to exit.)
            _last_ctrl_c_time[0] = now
            _ctrlc_hint_active[0] = True
        else:
            if now - _last_ctrl_c_time[0] < 1.0:
                logger.debug(
                    f"[handle_ctrl_c] double Ctrl+C detected: now={now}, last={_last_ctrl_c_time[0]}"
                )
                # print("[Olive] Exiting on double Ctrl+C.")
                buf = app.current_buffer
                print_info("gracefully exiting on double Ctrl+C. re-open olive shell anytime to pick up where you left off")
                buf.text = ":exit"
                buf.validate_and_handle()
                _last_ctrl_c_time[0] = now
                _ctrlc_hint_active[0] = True
                return
            else:
                # (Double Ctrl+C to exit) No input to clear
                _last_ctrl_c_time[0] = now
                _ctrlc_hint_active[0] = True
    except Exception as e:
        logger.exception("Exception in handle_ctrl_c: %s", e)
        print_error("Unexpected error during Ctrl+C handling. Shell remains alive.")


# Use Ctrl+Enter (ctrl-j) to insert a newline:
@bindings.add("c-j")
def insert_newline(event):
    """Insert a newline into the buffer."""
    event.app.current_buffer.insert_text("\n")


# Use plain Enter to submit:
@bindings.add("enter")
def submit(event):
    """Submit the current buffer."""
    event.app.current_buffer.validate_and_handle()


# (Optional) Keep escape+enter as a second “force submit”:
@bindings.add("escape", "enter")
def force_submit(event):
    """Force submission of input regardless of validation."""
    event.app.current_buffer.validate_and_handle()


# ─── Shell Session ─────────────────────────────────────────────────

session = PromptSession(
    completer=OliveCompleter(),
    key_bindings=bindings,
    style=style,
    multiline=True,
)
