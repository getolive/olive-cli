# cli/olive/tools/shell/guard.py
"""
olive.tools.shell.guard
=======================

Builds a *restricted* environment for the ``!!shell`` tool.

Key behaviours
--------------
•  Creates / reuses a shadow ``bin`` directory at::

       <project>/.olive/tmp/shell_guard_bin

   Every command listed under ``prefs.ai.tools.blacklist`` gets a tiny shell
   stub placed here.  The stub prints a 🚫 warning and exits with 127.

•  Prepends that directory to ``$PATH`` in a **copy** of the current
   ``os.environ`` so the calling process (sandbox daemon or REPL) remains
   unaffected.

The helpers rely exclusively on :pymod:`olive.env`, so the same code works
unchanged on the host and inside a sandbox container.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

from olive import env
from olive.preferences import prefs

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

# <project>/.olive/tmp/shell_guard_bin  (created lazily)
SHADOW_BIN: Path = env.get_dot_olive() / "tmp" / "shell_guard_bin"


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def build_safe_env() -> Dict[str, str]:
    """
    Return a **copy** of :pydata:`os.environ` with the shadow‑bin directory
    prepended to ``$PATH``.

    The original process environment is left untouched.

    Returns
    -------
    dict[str, str]
        Safe environment ready to be passed to :pyfunc:`subprocess.Popen`
        or :pyfunc:`asyncio.create_subprocess_exec`, etc.
    """
    env_vars: Dict[str, str] = os.environ.copy()
    blacklist = prefs.get("ai", "tools", "blacklist", default=[])

    SHADOW_BIN.mkdir(parents=True, exist_ok=True)

    for cmd in blacklist:
        fake = SHADOW_BIN / cmd
        if not fake.exists():
            # Create a very small shell script that blocks execution
            fake.write_text(
                "#!/bin/sh\n"
                f"echo \"\U0001f6d1  Command '{cmd}' is blocked by Olive preferences.\"\n"
                "exit 127\n"
            )
            fake.chmod(0o755)

    env_vars["PATH"] = f"{SHADOW_BIN}:{env_vars['PATH']}"
    return env_vars
