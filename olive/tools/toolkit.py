# olive/tools/toolkit.py
from typing import Callable, Optional

from pydantic import BaseModel


def olive_tool_management_command(name: Optional[str] = None):
    """
    Decorator to mark a function as a management command that should be registered
    into the Olive shell.

    Args:
        name (str): Optional shell command name (e.g., ':diff'). If not provided,
                    function name will be used as `:{func_name}`.

    Returns:
        Callable: Decorated function with `_olive_is_shell_command` and `_olive_command_name`
    """

    def decorator(fn: Callable):
        fn._olive_is_shell_command = True
        fn._olive_command_name = name or f":{fn.__name__.replace('_command', '')}"
        return fn

    return decorator


class ToolResponse(BaseModel):
    """
    A standardized response format for all Olive tools.

    Attributes:
        success (bool): Whether the tool execution was successful.
        stdout (Optional[str]): Standard output from the tool, if any.
        stderr (Optional[str]): Standard error output, if any.
        returncode (Optional[int]): Exit code of the tool process, if applicable.
        error (Optional[str]): Error message, if execution failed.
        reason (Optional[str]): Machine-readable reason for failure (e.g., 'mismatch', 'invalid', 'denied').
    """

    success: bool
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    returncode: Optional[int] = None
    error: Optional[str] = None
    reason: Optional[str] = None


def validate_invocation(
    invoked_tool_name: str, expected_tool_name: str
) -> Optional[ToolResponse]:
    """
    Ensure that the tool being executed matches the registered name for the tool.

    Args:
        invoked_tool_name (str): The name provided in the tool call.
        expected_tool_name (str): The name the tool expects.

    Returns:
        Optional[ToolResponse]: A failure response if names do not match; otherwise None.
    """
    if invoked_tool_name != expected_tool_name:
        return ToolResponse(
            success=False,
            reason="mismatch",
            error=f"Mismatched tool invocation: expected '{expected_tool_name}', got '{invoked_tool_name}'",
        )
    return None


def require_command(input: dict) -> Optional[ToolResponse]:
    """
    Validate that a 'command' key is present and non-empty in the tool input.

    Args:
        input (dict): The dictionary passed into run_tool().

    Returns:
        Optional[ToolResponse]: A failure response if 'command' is missing or empty; otherwise None.
    """
    cmd = input.get("command", "").strip()
    if not cmd:
        return ToolResponse(
            success=False, reason="invalid", error="Missing 'command' in tool input."
        )
    return None
