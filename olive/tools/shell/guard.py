# cli/olive/tools/shell/guard.py
import os
from olive.preferences import prefs
from olive.env import get_olive_base_path

SHADOW_BIN = get_olive_base_path() / "tmp" / "shell_guard_bin"


def build_safe_env() -> dict:
    """
    Create a safe environment with a shadow bin path that blocks blacklisted commands.
    """
    env = os.environ.copy()
    blacklist = prefs.get("ai", "tools", "blacklist", default=[])

    SHADOW_BIN.mkdir(parents=True, exist_ok=True)

    for cmd in blacklist:
        fake = SHADOW_BIN / cmd
        if not fake.exists():
            fake.write_text(
                f"#!/bin/sh\necho \"\U0001f6d1 Command '{cmd}' is blocked by Olive preferences.\"\nexit 127\n"
            )
            fake.chmod(0o755)

    env["PATH"] = f"{SHADOW_BIN}:{env['PATH']}"
    return env
