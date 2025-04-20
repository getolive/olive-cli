# cli/olive/tasks/runner.py

import json
import uuid

from olive.logger import get_logger
from olive.tasks.models import TaskResult, TaskSpec
from olive.tools import tool_registry
from olive.ui import console

logger = get_logger(__name__)


def run_task_from_file_json(task_path: str) -> str:
    """
    Like run_task_from_file but return the final JSON string
    (no spurious logs) for use by run_task_subprocess.
    """
    original = TaskSpec.load(task_path)
    runtime = TaskSpec(
        id=str(uuid.uuid4()),
        return_id=original.return_id,
        name=original.name,
        input=original.input,
    )
    tool = tool_registry.get(runtime.name)
    if not tool:
        raise RuntimeError(f"Tool '{runtime.name}' not found.")
    result = tool.run(json.dumps(runtime.input or {}))
    obj = TaskResult(output=result, status="completed")
    return json.dumps(obj.dict(), indent=2)


def run_task_from_file(task_path: str):
    """
    Execute a TaskSpec from disk.

    Olive assigns its own runtime-local `id` for task tracking.
    If the spec contains a `return_id`, the result will be written to:
    `.olive/run/tasks/results/<return_id>.json`.
    """
    original_spec = TaskSpec.load(task_path)

    runtime_spec = TaskSpec(
        id=str(uuid.uuid4()),  # 🧠 Discard incoming ID
        return_id=original_spec.return_id,
        name=original_spec.name,
        input=original_spec.input,
    )

    tool = tool_registry.get(runtime_spec.name)
    if not tool:
        raise RuntimeError(f"Tool '{runtime_spec.name}' not found or not allowed.")

    logger.info(
        f"[run-task] Running tool: {runtime_spec.name} (return_id={runtime_spec.return_id})"
    )
    result = tool.run(json.dumps(runtime_spec.input or {}))

    result_obj = TaskResult(output=result, status="completed")

    if runtime_spec.return_id:
        result_path = runtime_spec.result_path()
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(result_obj.dict(), indent=2))
        logger.info(f"[run-task] ✅ Result written to: {result_path}")
    else:
        console.print_json(json.dumps(result_obj.dict(), indent=2))
