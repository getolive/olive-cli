"""
olive.tools
───────────
• Discovers tool packages under `olive.tools.*`.
• Registers each as a `ToolEntry` (metadata + permissions).
• Exposes sync/async dispatch helpers wired into TaskManager.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Dict, List, Optional, Union

from rich import print  # noqa: TID251

from olive.logger import get_logger
from olive.preferences import prefs
from olive.tasks import task_manager

# Ensure system‑prompt injectors are imported once
from . import utils as _injectors  # noqa: F401  pylint: disable=unused-import
from .models import ToolDescription, ToolEntry
from .utils import extract_tool_calls

logger = get_logger("tools")


# ────────────────────────────────────────────────────────────────────────────────
# Registry class
# ────────────────────────────────────────────────────────────────────────────────


class ToolRegistry:
    """Singleton‑style registry that holds all discovered tools."""

    def __init__(self) -> None:
        self.entries: Dict[str, ToolEntry] = {}

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #

    def discover_all(self, install: bool = True) -> None:
        """
        Walk `olive.tools.*` sub‑packages and register any module exposing
        `describe_tool()`.  Respects prefs whitelist/blacklist.
        """
        tool_root = Path(__file__).parent
        mode = prefs.get("ai", "tools", "mode", default="blacklist")
        whitelist = set(prefs.get("ai", "tools", "whitelist", default=[]))
        blacklist = set(prefs.get("ai", "tools", "blacklist", default=[]))

        self.entries.clear()

        for _, name, ispkg in pkgutil.iter_modules([str(tool_root)]):
            if not ispkg:
                continue

            module_path = f"olive.tools.{name}"
            try:
                mod = importlib.import_module(module_path)
                describe = getattr(mod, "describe_tool", None)
                if not describe:
                    continue

                desc_data = describe()
                desc = ToolDescription(
                    name=name,
                    module=module_path,
                    description=desc_data.get("description"),
                    allowed_commands=desc_data.get("allowed_commands", []),
                    examples=desc_data.get("examples", []),
                )

                allowed, reason = self._evaluate_permissions(
                    name, mode, whitelist, blacklist
                )

                mgmt_cmds = self._load_management_commands(module_path)

                self.entries[name] = ToolEntry(
                    tool=desc,
                    allowed=allowed,
                    reason=reason,
                    management_commands=mgmt_cmds,
                )

            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to load tool '%s': %s", name, exc)
                self.entries[name] = ToolEntry(
                    tool=ToolDescription(name=name, module=module_path),
                    allowed=False,
                    reason=str(exc),
                )

        if install:
            self._register_prompt_commands()

    # .................................................................

    @staticmethod
    def _evaluate_permissions(
        name: str,
        mode: str,
        whitelist: set[str],
        blacklist: set[str],
    ) -> tuple[bool, str]:
        in_whitelist = name in whitelist
        in_blacklist = name in blacklist

        if mode == "whitelist":
            return in_whitelist, ("Whitelisted" if in_whitelist else "Not whitelisted")
        if mode == "blacklist":
            return (not in_blacklist), ("Blocked" if in_blacklist else "Allowed")
        return False, "Invalid mode in preferences"

    # .................................................................

    @staticmethod
    def _load_management_commands(
        module_path: str,
    ) -> Dict[str, callable]:  # noqa: ANN001
        cmds: Dict[str, callable] = {}
        try:
            admin_mod = importlib.import_module(f"{module_path}.admin")
            for attr_name in dir(admin_mod):
                fn = getattr(admin_mod, attr_name)
                if callable(fn) and getattr(fn, "_olive_is_shell_command", False):
                    cmd = getattr(fn, "_olive_command_name", f":{fn.__name__}")
                    cmds[cmd] = fn
        except ModuleNotFoundError:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to load shell commands from %s.admin: %s", module_path, exc
            )
        return cmds

    # .................................................................

    @staticmethod
    def _register_prompt_commands() -> None:
        try:
            from olive.prompt_ui import register_commands

            from . import tool_registry  # self‑import for type checking

            all_cmds = {
                cmd: fn
                for entry in tool_registry.list()
                for cmd, fn in entry.management_commands.items()
            }
            if all_cmds:
                register_commands(all_cmds)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to register prompt shell commands: %s", exc)

    # ------------------------------------------------------------------ #
    # Lookup helpers
    # ------------------------------------------------------------------ #

    def get(self, name: str) -> Optional[ToolEntry]:
        return self.entries.get(name)

    def list(self) -> List[ToolEntry]:
        return list(self.entries.values())

    # ------------------------------------------------------------------ #
    # Dispatch helpers
    # ------------------------------------------------------------------ #

    def dispatch(self, name: str, input_str: str) -> dict:
        """Run tool synchronously (host or sandbox, depending on prefs)."""
        entry = self.get(name)
        if not entry or not entry.allowed:
            raise RuntimeError(
                f"Tool '{name}' is not allowed: {entry.reason if entry else 'Not found'}"
            )
        return entry.run(input_str)

    def dispatch_async(self, name: str, input_str: str) -> str:
        """
        Schedule the tool invocation as an Olive background task.

        Returns
        -------
        task_id : str
            The TaskManager ID.  Await the result with
            `task_manager.wait_for_result(task_id)`.
        """
        entry = self.get(name)
        if not entry or not entry.allowed:
            raise RuntimeError(
                f"Tool '{name}' is not allowed: {entry.reason if entry else 'Not found'}"
            )

        async def _invoke() -> dict:  # zero‑arg coroutine factory
            return await entry.run_async(input_str)

        task_id = task_manager.create_task(
            name=f"tool:{name}",
            coro_factory=_invoke,
            input=input_str,
        )
        return task_id

    # ------------------------------------------------------------------ #
    # LLM prompt support (unchanged)
    # ------------------------------------------------------------------ #

    def build_llm_context_summary(self) -> str:
        """Return a structured, LLM‑friendly reference of callable Olive tools."""
        lines = [
            "🛠️ [Tool Usage Reference — for Olive's internal use]",
            "",
            "You have access to real tools. Wrap calls like:",
            "<olive_tool><tool>TOOL</tool><input>{JSON}</input></olive_tool>",
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]
        for e in sorted(self.list(), key=lambda t: t.tool.name):
            if not e.allowed:
                continue
            t = e.tool
            lines.append(f"\n🔹 **{t.name}** – {t.description or 'no description'}")
            if t.allowed_commands:
                lines.append(f"    Allowed: {', '.join(t.allowed_commands)}")
            if t.examples:
                lines.append("    Examples:")
                for ex in t.examples:
                    lines.append(f"      {ex}")
        lines.append("\nPrefer tools over free‑form guessing when possible.")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # LLM response post‑processing (unchanged)
    # ------------------------------------------------------------------ #

    def process_llm_response_with_tools(
        self, response: str, dispatch: bool = True
    ) -> Union[str, List[str]]:
        """
        Find <olive_tool> tags in an LLM response and optionally dispatch them.
        """
        matches = extract_tool_calls(response)

        print(f"[dim]🔍 Found {len(matches)} tool call(s). Dispatch={dispatch}[/dim]")

        if not matches:
            return response if not dispatch else []

        task_ids: List[str] = []

        for tool, inp in matches:
            tool = tool.strip()
            inp = inp.strip()

            if not dispatch:
                print(
                    f"\n[magenta]🛠 Detected Tool:[/magenta] {tool}\n[blue]Input:[/blue] {inp}"
                )
                continue

            try:
                tid = self.dispatch_async(tool, inp)
                task_ids.append(tid)
                print(f"[green]✅ Dispatched '{tool}' as task {tid}[/green]")
            except Exception as exc:  # noqa: BLE001
                print(f"[red]❌ Failed to dispatch '{tool}': {exc}[/red]")

        return task_ids if dispatch else response


# ---------------------------------------------------------------------------
# Singleton instance
# ---------------------------------------------------------------------------

tool_registry = ToolRegistry()
