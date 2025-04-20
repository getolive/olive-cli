# cli/olive/tools/utils.py

import re
import xml.etree.ElementTree as ET
from typing import List, Tuple

from olive.context.injection import olive_context_injector
from olive.logger import get_logger

logger = get_logger("tools.utils")


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
    Robustly pull out every <olive_tool>…</olive_tool> block and return
    (tool_name, input_json) pairs.

    • Ignores whitespace / newlines / attributes.
    • Silently skips malformed blocks.
    """
    blocks = re.findall(
        r"<olive_tool\b[^>]*>(.*?)</olive_tool>",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    calls: List[Tuple[str, str]] = []
    for raw in blocks:
        try:
            xml_fragment = f"<root>{raw}</root>"  # wrap so it's valid XML
            root = ET.fromstring(xml_fragment)
            tool = root.findtext(".//tool").strip()
            inp = root.findtext(".//input")
            if tool and inp is not None:
                calls.append((tool, inp.strip()))
        except ET.ParseError:
            # Skip ill‑formed XML silently
            continue
    return calls
