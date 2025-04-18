# cli/olive/tools/models.py
"""Tool registry entry – now always persists its TaskSpec/TaskResult."""

import json
import uuid
import importlib
import asyncio
from typing import Callable, Dict, List, Optional

from pydantic import BaseModel

from olive.logger import get_logger
from olive.preferences import prefs
from olive.tasks.models import TaskResult, TaskSpec, TaskStatus
from olive.sandbox import sandbox

logger = get_logger("tools")


class ToolDescription(BaseModel):
    name: str
    module: str
    description: Optional[str] = None
    allowed_commands: List[str] = []
    examples: List[str] = []


class ToolEntry(BaseModel):
    tool: ToolDescription
    allowed: bool
    reason: str
    management_commands: Dict[str, Callable] = {}

    # --------------------------------------------------------------
    # Public API
    # --------------------------------------------------------------
    def run(self, input_str: str) -> dict:  # noqa: D401
        """Synchronous invoke (local or sandbox) with automatic persistence."""
        data = self._parse_input(input_str)
        if self._should_use_sandbox():
            return self._run_in_sandbox(data)
        return self._run_local(data)

    async def run_async(self, input_str: str):
        return await asyncio.to_thread(self.run, input_str)

    # --------------------------------------------------------------
    # Internals
    # --------------------------------------------------------------
    def _parse_input(self, raw: str) -> dict:  # unchanged helper
        try:
            val = raw.strip()
            if val.startswith("'") and val.endswith("'"):
                val = val[1:-1]
            parsed = json.loads(val)
            if not isinstance(parsed, dict):
                raise ValueError("Input JSON is not an object")
            return parsed
        except Exception:  # noqa: BLE001 – fallback shell‑style
            return {"command": raw.strip()}

    # ..........................................................
    def _run_local(self, input_data: dict) -> dict:
        logger.info("[tool] Running '%s' locally", self.tool.name)
        mod = importlib.import_module(self.tool.module)
        if not hasattr(mod, "run_tool"):
            raise RuntimeError(f"Tool '{self.tool.name}' missing run_tool()")

        raw_output = mod.run_tool(input_data)
        # persist spec & result ALWAYS
        spec = TaskSpec(name=self.tool.name, input=input_data)
        spec.save()
        TaskResult(output=raw_output, status=TaskStatus.COMPLETED).save(spec)
        return raw_output

    # ..........................................................
    def _run_in_sandbox(self, input_data: dict) -> dict:
        # guarantee return_id so sandbox can locate its result
        input_data.setdefault("return_id", str(uuid.uuid4()))
        spec = TaskSpec(
            return_id=input_data["return_id"], name=self.tool.name, input=input_data
        )
        return sandbox.dispatch_task(spec)

    # ..........................................................
    def _should_use_sandbox(self) -> bool:
        return prefs.is_sandbox_enabled()
