# cli/olive/tools/utils.py

import re
from typing import List, Any

from pydantic import ValidationError
from olive.context.injection import olive_context_injector
from olive.logger import get_logger


logger = get_logger("tools.utils")

_OLIVE_BLOCK_RE = re.compile(
    r"<olive_tool\b[^>]*>(.*?)</olive_tool>",  # non‑greedy: grabs each block
    flags=re.IGNORECASE | re.DOTALL,
)

# extract <tool>…</tool>   then   <input> … </input>
#    • tolerant of attrs / whitespace
#    • if </input> is absent, capture runs to end-of-block ($)
_TOOL_INPUT_RE = re.compile(
    r"<tool\b[^>]*>(.*?)</tool>"          # 1️⃣ tool name
    r"[\s\S]*?"                           #     anything up to <input>
    r"<input\b[^>]*>"                     #     input tag
    r"([\s\S]*?)"                         # 2️⃣ payload
    r"(?:</input\b[^>]*>|$)",             # stop at </input> or end-of-block
    flags=re.IGNORECASE | re.DOTALL,
)

_INTENT_RE = re.compile(
    r"<intent\b[^>]*>(.*?)</intent>|"  # long form
    r"<intent\b[^>]*\bvalue=['\"](.*?)['\"][^>]*/?>",  # self-closing
    flags=re.IGNORECASE | re.DOTALL,
)


@olive_context_injector(role="system")
def render_tools_context_for_llm() -> List[str]:
    """
    Inject a concise summary of available tools into Olive's system prompt.

    This allows the LLM to understand which tools exist, what they can do,
    and how to call them effectively using the function call protocol.

    Returns:
        List[dict]: A list with one or more system messages formatted as
                    {'role': 'system', 'content': ...}
    """
    from olive.tools import tool_registry

    try:
        summary = tool_registry.build_llm_context_summary()
        logger.info("Injected tool usage summary into system prompt.")
        return [summary]
    except Exception as e:
        logger.exception(f"Failed to inject tool summary into system prompt: {e}")
        return []


# ──────────────────────────────
# Public API
# ──────────────────────────────
def extract_tool_calls(text: str) -> List[Any]:
    """
    Extract <olive_tool> … </olive_tool> blocks and return validated ToolCall objects.

    • Ignores malformed blocks gracefully.
    • Still regex-only: fast and tolerant of raw '<' / '>' inside <input>.
    """
    from .models import ToolCall
    calls: List[ToolCall] = []

    for block in _OLIVE_BLOCK_RE.findall(text):
        ti_match = _TOOL_INPUT_RE.search(block)
        if not ti_match:
            continue  # skip if tool/input missing

        tool = ti_match.group(1).strip()
        inp = ti_match.group(2).strip()

        intent_match = _INTENT_RE.search(block)
        intent = (
            (intent_match.group(1) or intent_match.group(2)).strip()
            if intent_match
            else ""
        )

        try:
            calls.append(ToolCall(tool_name=tool, intent=intent, tool_input=inp))
        except ValidationError as e:
            logger.warning("Skipping malformed tool call: %s", e)

    return calls
