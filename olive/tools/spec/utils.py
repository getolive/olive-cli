# cli/olive/tools/spec/utils.py
import yaml
from olive.canonicals.spec.storage import get_all_specs
from olive.canonicals.spec.models import FeatureSpec
from olive.tools.spec.state import get_active_spec_id
from olive.preferences import prefs
from pathlib import Path
from olive.logger import get_logger
from typing import List
from olive.context.injection import olive_context_injector


logger = get_logger(__name__)

@olive_context_injector(role="system")
def render_spec_context_for_llm() -> List[str]:
    messages = []
    active_id = get_active_spec_id()

    # Add builder strategy prompt (if there is an active spec)
    # If not we just add the specs.
    if active_id:
        prompt_path = Path(
            prefs.get(
                "builder_mode",
                "prompt_path",
                default="~/.olive/builder_mode_prompt.txt",
            )
        ).expanduser()
        if prompt_path.exists():
            builder_mode_prompt = prompt_path.read_text().strip()
            messages.append(builder_mode_prompt)
            logger.info(
                f"Injected the Builder Mode system prompt from {prompt_path} ({len(builder_mode_prompt)} chars)"
            )

    # Load all specs
    specs = get_all_specs()

    # Explain the inclusion of specs.
    if len(specs) > 0:
        content = """\
# 🧭 Working with Specs in Olive

Specs define units of work you are responsible for. You must understand, reference, and update the current active spec as you work. Only one spec is active at a time.

### Why Specs Matter
- Specs anchor your actions and clarify goals
- They track subtasks, code paths, and progress
- Specs may be user stories, tasks, epics, or broader initiatives
- Olive prefers to summarize intent and work as specs

### Your Responsibilities
- Always know which spec is active
- Ask the user if you're unsure or need to switch
- Keep each spec clean, outcome-focused, and up to date
- Use subtasks to break down and track work
- Use the `spec` tool to read, update, complete, cancel

### Display Legend
- 🟢 Active spec
- 🔵 Open specs (newest first)
- ⚪ In-progress
- ✅ Complete
- ❌ Cancelled

Specs below are sorted by relevance:
"""
        content += _summarize_specs_for_llm(specs, active_id)
        messages.append(content)

    return messages


def _summarize_specs_for_llm(specs: list[FeatureSpec], active_id: str | None) -> str:
    if not specs:
        return "\n_No specs defined._"

    # Custom sort logic
    def sort_key(spec: FeatureSpec):
        status_rank = {
            "open": 0,
            "in-progress": 1,
            "complete": 2,
            "cancelled": 3,
        }
        is_active = spec.id == active_id
        return (
            0 if is_active else 1,
            status_rank.get(spec.status, 99),
            -spec.created_at.timestamp(),
        )

    specs_sorted = sorted(specs, key=sort_key)
    lines = []

    for spec in specs_sorted:
        icon = (
            "🟢"
            if spec.id == active_id
            else "🔵"
            if spec.status == "open"
            else "⚪"
            if spec.status == "in-progress"
            else "✅"
            if spec.status == "complete"
            else "❌"
        )

        title_line = f"{icon} [{spec.id}] {spec.title}"

        if spec.id == active_id:
            detail = spec.model_dump(exclude_none=True)
            lines.append(
                f"{title_line} (active)\n```yaml\n{yaml.safe_dump(detail, sort_keys=False)}\n```"
            )
        else:
            lines.append(f"{title_line} ({len(spec.subtasks)} subtasks)")

    return "\n".join(lines)
