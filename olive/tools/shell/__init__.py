# cli/olive/tools/shell/__init__.py
import shlex
import subprocess

from olive.logger import get_logger
from olive.tools import ToolDescription
from olive.tools.permissions import is_command_allowed
from olive.tools.toolkit import ToolResponse, require_command, validate_invocation

from .guard import build_safe_env

TOOL_NAME = "shell"  # Single source of truth
logger = get_logger(f"tools.{TOOL_NAME}")


def describe_tool() -> ToolDescription:
    return {
        "name": TOOL_NAME,
        "description": "Run safe shell commands through Olive.",
        "allowed_commands": [],  # Display-only: populated dynamically
        "examples": [
            "<olive_tool><tool>shell</tool><intent>Review file listing details to decide where to begin.</intent><input>ls -la</input></olive_tool>",
        ],
    }


def run_tool(input: dict, invoked_tool_name: str = TOOL_NAME) -> dict:
    """
    Execute a shell command, with tool name validation and permission enforcement.
    """
    mismatch = validate_invocation(invoked_tool_name, TOOL_NAME)
    if mismatch:
        return mismatch.dict()

    missing = require_command(input)
    if missing:
        return missing.dict()

    command = input["command"].strip()

    try:
        cmd_name = shlex.split(command)[0]
    except Exception as e:
        return ToolResponse(success=False, error=f"Failed to parse command: {e}").dict()

    allowed, reason = is_command_allowed(TOOL_NAME, command)
    if not allowed:
        return ToolResponse(success=False, error=f"{cmd_name}: {reason}").dict()

    logger.info(f"[{TOOL_NAME}] Running command: {command}")
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, env=build_safe_env()
        )
        return ToolResponse(
            success=True,
            stdout=result.stdout.strip(),
            stderr=result.stderr.strip(),
            returncode=result.returncode,
        ).dict()
    except Exception as e:
        logger.exception(f"[{TOOL_NAME}] Subprocess execution failed.")
        return ToolResponse(success=False, error=str(e)).dict()
