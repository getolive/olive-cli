# cli/olive/tools/spec/__init__.py
"""
The `spec` tool manages structured feature specifications in Olive.

Supports creation, activation, elaboration (e.g. subtasks, comments),
and progress tracking for goal-oriented work in Builder Mode.

This version de-couples spec tracking from Git, and supports direct
state management via `.olive/specs/` and `.olive/state/active_spec.yml`.
"""

from pathlib import Path

import yaml

from olive.canonicals.spec.models import FeatureSpec
from olive.canonicals.spec.storage import get_all_specs
from olive.logger import get_logger
from olive.tools.spec.state import get_active_spec_id, set_active_spec_id
from olive.tools.toolkit import ToolResponse, require_command, validate_invocation

# Ensure system prompt injectors are registered
from . import utils as _injectors  # noqa: F401

TOOL_NAME = "spec"
SPECS_DIR = Path(".olive/specs/")
logger = get_logger(f"tools.{TOOL_NAME}")


def describe_tool():
    return {
        "name": TOOL_NAME,
        "description": (
            "Manage feature specs — structured units of work that describe goals, steps, and progress.\n\n"
            "Use specs to drive Builder Mode, track tasks, and keep Olive aligned with project objectives.\n\n"
            "Supported commands:\n"
            "- create: Create a new spec with title and description.\n"
            "- list: List all saved specs, showing current active spec.\n"
            "- get: Return a full spec by ID.\n"
            "- set-active: Set a spec as the active Builder Mode target.\n"
            "- get-active: Show which spec is currently active.\n"
            "- update: Update metadata fields like title, priority, etc.\n"
            "- add-subtask: Append a checklist item to a spec.\n"
            "- complete-subtask: Mark a specific subtask as complete.\n"
            "- add-comment: Leave a human-readable comment on the spec.\n"
            "- cancel: Mark a spec as cancelled (soft archival).\n"
            "- complete: Mark a spec as complete (used for closeout).\n\n"
            "Builder Mode activates when a spec is active — use it to focus Olive on your current goal."
        ),
        "allowed_commands": [],
        "examples": [
            '<olive_tool><tool>spec</tool><intent>Spec out builder mode.</intent><input>{"command": "create", "title": "Add Builder Mode", "description": "Enable spec-driven execution"}</input></olive_tool>',
            '<olive_tool><tool>spec</tool><intent>Close the builder mode spec.</intent><input>{"command": "complete", "spec_id": "20250408_092300"}</input></olive_tool>',
            '<olive_tool><tool>spec</tool><intent>Cancel the builder mode spec.</intent><input>{"command": "cancel", "spec_id": "20250408_092300"}</input></olive_tool>',
            '<olive_tool><tool>spec</tool><intent>Review the available specs.</intent><input>{"command": "list"}</input></olive_tool>',
            '<olivektool><tool>spec</tool><intent>Review spec details.</intent><input>{"command": "get", "spec_id": "20250408_092300"}</input></olive_tool>',
            '<olive_tool><tool>spec</tool><intent>Get the active spec.</intent><input>{"command": "get-active"}</input></olive_tool>',
            '<olive_tool><tool>spec</tool><intent>Get to work on builder mode spec, setting active..</intent><input>{"command": "set-active", "spec_id": "20250408_092300"}</input></olive_tool>',
            '<olive_tool><tool>spec</tool><intent>Making the title better and updating to high priority</intent><input>{"command": "update", "spec_id": "20250408_092300", "title": "New Title", "priority": "high"}</input></olive_tool>',
            '<olive_tool><tool>spec</tool><intent>Creating a sub-task for builder for prompt injection mgt</intent><input>{"command": "add-subtask", "spec_id": "20250408_092300", "task": "Inject spec into prompt"}</input></olive_tool>',
            '<olive_tool><tool>spec</tool><intent>Updating the spec to mark prompt injection done.</intent><input>{"command": "complete-subtask", "spec_id": "20250408_092300", "index": 0}</input></olive_tool>',
            '<olive_tool><tool>spec</tool><intent></intent>Adding a git decouple comment to remember for later<input>{"command": "add-comment", "spec_id": "20250408_092300", "comment": "Let\'s start with removing git coupling."}</input></olive_tool>',
        ],
    }


def run_tool(input: dict, invoked_tool_name: str = TOOL_NAME) -> dict:
    mismatch = validate_invocation(invoked_tool_name, TOOL_NAME)
    if mismatch:
        return mismatch.dict()

    missing = require_command(input)
    if missing:
        return missing.dict()

    command = input["command"].strip()
    logger.info(f"[spec] Received command: {command}")

    try:
        if command == "create":
            spec = FeatureSpec.create(
                title=input.get("title", ""), description=input.get("description", "")
            )
            logger.info(f"Created new spec: {spec.id}")
            return ToolResponse(success=True, stdout=f"Created spec {spec.id}").dict()

        elif command == "get":
            spec_id = input.get("spec_id")
            if not spec_id:
                return ToolResponse(
                    success=False, reason="missing-id", error="Missing 'spec_id'"
                ).dict()
            try:
                spec = FeatureSpec.load(spec_id)
                return ToolResponse(success=True, stdout=spec.dict()).dict()
            except Exception as e:
                logger.warning(f"Failed to load spec {spec_id}: {e}")
                return ToolResponse(
                    success=False, reason="load-failed", error=str(e)
                ).dict()

        elif command == "complete":
            spec = FeatureSpec.load(input.get("spec_id"))
            spec.status = "complete"
            spec.save()
            logger.info(f"Marked spec {spec.id} complete.")
            return ToolResponse(
                success=True, stdout=f"Marked spec {spec.id} complete"
            ).dict()

        elif command == "cancel":
            spec = FeatureSpec.load(input.get("spec_id"))
            spec.status = "cancelled"
            spec.save()
            logger.info(f"Cancelled spec {spec.id}")
            return ToolResponse(success=True, stdout=f"Cancelled spec {spec.id}").dict()

        elif command == "list":
            current_spec_id = get_active_spec_id()
            specs = [spec.model_dump(exclude_none=True) for spec in get_all_specs()]

            return ToolResponse(
                success=True,
                stdout=yaml.safe_dump(
                    {"current_spec_id": current_spec_id, "specs": specs},
                    sort_keys=False,
                ),
            ).dict()

        elif command == "get-active":
            active_id = get_active_spec_id()
            logger.info(f"Queried active spec: {active_id}")
            return ToolResponse(
                success=True, stdout=f"Active spec: {active_id or 'None'}"
            ).dict()

        elif command == "set-active":
            spec_id = input.get("spec_id")
            if not spec_id:
                return ToolResponse(success=False, error="Missing `spec_id`").dict()
            set_active_spec_id(spec_id)
            logger.info(f"Set active spec to: {spec_id}")
            return ToolResponse(
                success=True, stdout=f"Set active spec to: {spec_id}"
            ).dict()

        elif command == "update":
            spec = FeatureSpec.load(input.get("spec_id"))
            updated_fields = []

            for field in ("title", "description", "value_case", "priority"):
                if field in input:
                    setattr(spec, field, input[field])
                    updated_fields.append(field)

            spec.save()
            logger.info(f"Updated fields {updated_fields} for spec {spec.id}")
            return ToolResponse(
                success=True, stdout=f"Updated fields: {', '.join(updated_fields)}"
            ).dict()

        elif command == "add-subtask":
            spec = FeatureSpec.load(input.get("spec_id"))
            task = input.get("task")
            if not task:
                return ToolResponse(success=False, error="Missing `task`").dict()
            spec.subtasks.append({"task": task, "done": False})
            spec.save()
            logger.info(f"Added subtask to spec {spec.id}: {task}")
            return ToolResponse(success=True, stdout=f"Added subtask: {task}").dict()

        elif command == "complete-subtask":
            spec = FeatureSpec.load(input.get("spec_id"))
            task_index = input.get("index")
            if task_index is None or not isinstance(task_index, int):
                return ToolResponse(
                    success=False, error="Missing or invalid `index`"
                ).dict()

            try:
                spec.subtasks[task_index]["done"] = True
                spec.save()
                logger.info(f"Marked subtask #{task_index} complete for spec {spec.id}")
                return ToolResponse(
                    success=True, stdout=f"Subtask {task_index} marked complete."
                ).dict()
            except IndexError:
                return ToolResponse(
                    success=False, error="Subtask index out of range"
                ).dict()

        elif command == "add-comment":
            spec = FeatureSpec.load(input.get("spec_id"))
            comment = input.get("comment", "").strip()
            if not comment:
                return ToolResponse(success=False, error="Missing `comment`").dict()
            spec.comments.append(comment)
            spec.save()
            logger.info(f"Added comment to spec {spec.id}: {comment}")
            return ToolResponse(success=True, stdout="Comment added.").dict()

        return ToolResponse(
            success=False, reason="unknown-command", error=f"Unknown command: {command}"
        ).dict()

    except Exception as e:
        logger.exception(
            f"[spec] Exception occurred while processing command: {command}"
        )
        return ToolResponse(success=False, reason="exception", error=str(e)).dict()
