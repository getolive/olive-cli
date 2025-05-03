# cli/olive/context/models.py
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ContextFile(BaseModel):
    path: str
    lines: List[str]


class ASTEntry(BaseModel):
    """
    A single structural element extracted from a file.
    Meant for LLM use, not exhaustive compiler fidelity.
    """

    name: str
    type: str
    location: str  # e.g., "path/to/file.py:12–34"
    summary: Optional[str] = None  # Short natural language description or docstring
    code: Optional[str] = None  # Snippet of the raw source
    # allow arbitrary JSON-serialisable metadata; safe default factory; decorators, calls, returns, etc.
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class Context(BaseModel):
    """
    The canonical state of Olive's context — persisted, inspected, injected into the LLM.
    """

    system: List[str] = []  # System prompt blocks (files, rules, etc)
    chat: List[ChatMessage] = []  # Recent chat history
    files: List[ContextFile] = []  # Files sent or to be sent
    extra_files: List[ContextFile] = []  # Additional files typically managed via @ commands (e.g., context.add_extra_file)
    metadata: Dict[str, List[ASTEntry]] = {}  # Structural summaries (per file)
    imports: Dict[str, List[str]] = {}  # Top-level imports (per file)
    version: str = "1.0"  # For future-proofing migrations
