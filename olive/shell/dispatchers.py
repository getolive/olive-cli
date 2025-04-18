# olive/shell/dispatchers.py

import shlex
import inspect
import subprocess
from rich.markup import MarkupError

from olive.ui import console, print_error, print_warning, print_success
from olive.llm import LLMProvider
from olive.logger import get_logger
from olive.prompt_ui import get_management_commands
from olive.tools import tool_registry
from olive.tasks import task_manager

from .utils import _render_tool_result

logger = get_logger(__name__)
llm = LLMProvider()
COMMANDS = get_management_commands()


async def dispatch(user_input: str, interactive: bool):
    """
    Route input based on its prefix:
      :   management command
      !!  async tool call
      !   shell exec
      else → LLM fallback
    """
    user_input = user_input.strip()
    if not user_input:
        return

    if user_input.startswith(":"):
        return await _dispatch_management(user_input, interactive)

    if user_input.startswith("!!"):
        return await _dispatch_tool_call(user_input, interactive)

    if user_input.startswith("!"):
        _dispatch_shell_exec(user_input[1:])
        return

    return await _dispatch_llm(user_input, interactive)


async def _dispatch_management(user_input: str, interactive: bool):
    """
    Look up and invoke a registered management command.
    """
    parts = user_input.split(maxsplit=1)
    cmd_name = parts[0]
    args = parts[1] if len(parts) > 1 else None

    if cmd_name in COMMANDS:
        if interactive:
            console.print(
                f"[primary]🛠️ Running command:[/primary] [secondary]{cmd_name}[/secondary]"
            )
            console.print()
        try:
            fn = COMMANDS[cmd_name]
            if inspect.iscoroutinefunction(fn):
                result = await (fn(args) if args else fn())
            else:
                result = fn(args) if args else fn()
            if not interactive:
                return result
        except Exception as e:
            logger.exception(f"Command error: {cmd_name}")
            if interactive:
                print_error(f"Command error: {e}")
        return

    if interactive:
        print_warning(f"Unknown command: {cmd_name}")
    logger.warning(f"Unknown shell command: {cmd_name}")


async def _dispatch_tool_call(user_input: str, interactive: bool):
    """
    Dispatch an async tool invocation via `!!tool_name [args]`.
    Show a spinner while we wait, then clear it and print the final result.
    """
    # parse out the tool name + args
    _, rest = user_input.split("!!", 1)
    parts = rest.strip().split(maxsplit=1)
    tool_name = parts[0]
    tool_input = parts[1] if len(parts) > 1 else ""

    try:
        task_id = tool_registry.dispatch_async(tool_name, tool_input)
        logger.info(f"Dispatched tool '{tool_name}' as task {task_id}")

        if interactive:
            print_success(f"Tool dispatched as background task: {task_id}")

            with console.status("[highlight]Thinking…[/highlight]", spinner="dots"):
                result = await task_manager.wait_for_result(task_id)

            _render_tool_result(result)
            return result

        # non‑interactive callers just get back the raw result
        result = await task_manager.wait_for_result(task_id)
        return result

    except Exception as e:
        logger.exception(f"Tool error ({tool_name})")
        if interactive:
            print_error(f"Tool '{tool_name}' failed: {e}")


async def _dispatch_llm(user_input: str, interactive: bool):
    """
    Send any plain input to the LLM as a fallback.
    """
    logger.info("User prompt:\n%s", user_input)
    response = await llm.ask(user_input)
    logger.info("Olive response:\n%s", response)

    if interactive:
        try:
            console.print(f"[prompt]🤖[/prompt] [primary]{response}[/primary]\n")
        except MarkupError:
            print_warning(f":warning:⚠️ 🤖 {response}\n")
    else:
        return response


def _dispatch_shell_exec(command: str):
    """
    Execute a shell command — interactive shells (vim, less, etc.) get direct tty;
    others capture output.
    """
    try:
        args = shlex.split(command)
        interactive_cmds = {"nvim", "vim", "htop", "less", "more", "top", "man"}
        base = args[0] if args else ""

        if base in interactive_cmds:
            logger.info(f"Running interactive shell command: {command}")
            subprocess.run(command, shell=True)
        else:
            logger.info(f"Running shell command: {command}")
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            if result.stdout:
                console.print(result.stdout, end="")
            if result.stderr:
                print_error(result.stderr)

    except Exception as e:
        print_error(f"Shell command failed: {e}")
        logger.exception(f"Shell command error: {e}")
