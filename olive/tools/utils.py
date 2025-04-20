# cli/olive/tools/utils.py

import re
from typing import List, Tuple

from olive.context.injection import olive_context_injector
from olive.logger import get_logger

logger = get_logger("tools.utils")

_OLIVE_BLOCK_RE = re.compile(
    r"<olive_tool\b[^>]*>(.*?)</olive_tool>",  # non‑greedy: grabs each block
    flags=re.IGNORECASE | re.DOTALL,
)

_TOOL_INPUT_RE = re.compile(
    r"<tool>(.*?)</tool>.*?<input>([\s\S]*?)</input>",
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


def extract_tool_calls(text: str) -> List[Tuple[str, str]]:
    """
    Return a list of (tool_name, input_payload) tuples.

    • Robust to raw '<' '>' inside <input>.
    • Ignores malformed blocks gracefully.
    • No XML parsing; pure regex, so it's fast and tolerant.
    """
    calls: List[Tuple[str, str]] = []
    for block in _OLIVE_BLOCK_RE.findall(text):
        m = _TOOL_INPUT_RE.search(block)
        if not m:
            continue  # skip malformed / partial blocks
        tool, inp = m.group(1).strip(), m.group(2).strip()
        if tool and inp:
            calls.append((tool, inp))
    return calls
