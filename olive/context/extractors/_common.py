from pathlib import Path
from olive.context.models import ASTEntry
from olive.env import get_project_root


def make_entry(
    *,
    name: str,
    typ: str,
    path: Path,
    start: int,
    end: int,
    summary: str = "",
    code: str = "",
    meta: dict | None = None,
) -> ASTEntry:
    """
    Standard ASTEntry factory.

    • location  →  'file.py:7–18'
    • metadata  →  always contains 'start'/'end'
    """
    md = {"start": start, "end": end}
    if meta:
        md.update(meta)

    return ASTEntry(
        name=name,
        type=typ,
        location=f"{path}:{start}–{end}",
        summary=summary,
        code=code,
        metadata=md,
    )


# ── helpers ─────────────────────────────────────────────────────────────
def _rel_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(get_project_root()))
    except ValueError:
        return str(path)
