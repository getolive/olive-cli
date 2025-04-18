# olive/tools/permissions.py
import shlex
from typing import Tuple
from olive.preferences import prefs

def is_command_allowed(tool: str, command: str) -> Tuple[bool, str]:
    """
    Decide if a command is allowed for a tool.
    Returns (allowed: bool, reason: str).
    """
    mode = prefs.get("ai", "tools", "mode", default="blacklist")
    whitelist = set(prefs.get("ai", "tools", "whitelist", default=[]))
    blacklist = set(prefs.get("ai", "tools", "blacklist", default=[]))

    try:
        cmd_name = shlex.split(command)[0]
    except Exception:
        return False, "Could not parse command"

    if mode == "whitelist":
        if cmd_name in whitelist:
            return True, "Whitelisted"
        return False, f"'{cmd_name}' is not whitelisted"

    if mode == "blacklist":
        if cmd_name in blacklist:
            return False, f"'{cmd_name}' is blacklisted"
        return True, "Allowed"

    if mode == "yolo":
        return True, "Allowed in YOLO mode"

    return False, "Unknown tool mode"

