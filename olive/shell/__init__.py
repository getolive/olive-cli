# olive/shell/__init__.py
import subprocess
from olive.shell import admin as shell_admin  # noqa
from olive.tasks import admin as tasks_admin  # noqa
from olive.sandbox import admin as sandbox_admin  # noqa
from olive.canonicals import admin as canonicals_admin  # noqa
import olive.tools.admin  # noqa # ensure toolkit/tool management commands are registered
from olive.ui import print_info, print_error
from olive.logger import get_logger
from olive.daemon import process_manager
from olive.shell.dispatchers import dispatch
from olive.voice.manager import voice_manager
from olive.prompt_ui import (
    session,
    olive_prompt,
    register_commands,
    get_management_commands,
    olive_management_command,
)

logger = get_logger(__name__)


# Voice management commands
@olive_management_command("voice-enable")
async def voice_enable_command(*args):
    voice_manager.enable()


@olive_management_command("voice-disable")
async def voice_disable_command(*args):
    voice_manager.disable()


@olive_management_command("voice-toggle")
async def voice_toggle_command(*args):
    voice_manager.toggle()


@olive_management_command("voice-status")
async def voice_status_command(*args):
    status = voice_manager.get_status()
    print_info(f"Voice pipeline status: {status}")


async def run_shell_command(command: str):
    """
    Used by `olive shell -c …` to forward into an existing daemon if possible,
    or run locally otherwise.
    """
    daemons = process_manager.list()
    alive = [d for d in daemons.values() if d.kind == "shell" and d.is_alive()]

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
        return await dispatch(command, interactive=False)


async def run_interactive_shell():
    from olive.init import initialize_shell_session

    initialize_shell_session()
    register_commands(get_management_commands())
    while True:
        try:
            user_input = await session.prompt_async(olive_prompt)
            await dispatch(user_input, interactive=True)
        except (KeyboardInterrupt, EOFError):
            print_info("\nExiting Olive Shell.")
            logger.info("Shell exited by user.")
            break
