# olive/shell/__init__.py

import subprocess

from olive.logger import get_logger
from olive.daemon import process_manager
from olive.ui import print_error, print_info
from olive.shell.dispatchers import dispatch
from olive.init import initialize_shell_session
from olive.prompt_ui import olive_prompt, session

# ensure all admin commands get registered
import olive.shell.admin  # noqa: F401

logger = get_logger("shell")


async def handle_shell_input(user_input: str, interactive: bool = True):
    """
    Top‑level entry for each line of input.
    Strips and ignores empty input, then hands off to the dispatcher.
    """
    text = user_input.strip()
    if not text:
        return
    return await dispatch(text, interactive)


async def run_interactive_shell():
    """
    The main loop: initialize, then repeatedly prompt & dispatch.
    """
    initialize_shell_session()
    while True:
        try:
            user_input = await session.prompt_async(olive_prompt)
            await handle_shell_input(user_input, interactive=True)
        except (KeyboardInterrupt, EOFError):
            print_info("\nExiting Olive Shell.")
            logger.info("Shell exited by user.")
            break


async def run_shell_command(command: str):
    """
    Used by `olive shell -c …` to forward into an existing daemon if possible,
    or run locally otherwise.
    """
    daemons = process_manager.list()
    alive = [d for d in daemons.values() if d.type == "shell" and d.is_alive()]

    if len(alive) == 1:
        daemon = alive[0]
        logger.info(f"Forwarding to daemon: {daemon.daemon_id}")
        try:
            subprocess.run(
                ["tmux", "send-keys", "-t", daemon.daemon_id, command, "C-m"],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            print_error(f"Failed to send to daemon: {e}")

    elif len(alive) > 1:
        print_error("❌ Multiple daemons detected. Specify with --daemon-id.")

    else:
        print_info("⚙️ No daemon found; running locally…")
        return await handle_shell_input(command, interactive=False)
