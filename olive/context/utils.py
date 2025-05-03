# cli/olive/context/utils.py

import subprocess
from pathlib import Path

from olive.context.injection import olive_context_injector
from olive.env import get_project_root
from olive.logger import get_logger
from olive.preferences.admin import get_prefs_lazy
from olive.context.models import ASTEntry


logger = get_logger(__name__)


@olive_context_injector(role="user")
def render_file_context_for_llm() -> list[str]:
    """
    Build the prompt fragments that Olive feeds into the LLM.

    ── Modes ───────────────────────────────────────────────────────────
      • Abstract  → concise AST summaries (after roll-up filters)
      • Raw       → full file bodies
      • Extra     → always raw, always appended

    All heavy lifting (Tailwind collapse, HTML skeleton, …) now lives in
    `olive.context.rollups` plug-ins, keeping this function tiny.
    """

    from olive.context import context  # lazy import to avoid cycles
    from olive.context.extractors import ROLLUPS

    prefs = get_prefs_lazy()
    logger = get_logger(__name__)
    out: list[str] = []

    _DEDUPE = ROLLUPS["*"]

    # ── helpers ────────────────────────────────────────────────────────
    def _short(loc):
        return loc.split(":", 1)[1] if ":" in loc else loc

    def _apply_rollup(entries: list[ASTEntry], path: str) -> list[ASTEntry]:
        """Language-specific → outline-expander → dedupe."""
        fn_lang = ROLLUPS.get(Path(path).suffix.lower())
        if fn_lang:
            entries = list(fn_lang(entries, path))

        entries = list(ROLLUPS["outline"](entries, path))  # NEW
        return list(_DEDUPE(entries, path))

    # NEW ▸ format a single ASTEntry -----------------------------------
    def _render(e: ASTEntry) -> str:
        """
        One-liner for a single ASTEntry.

        Order of precedence
        -------------------
        1. file_header    → “[1:N] file.py (1.23 kb)”
        2. outline_line   → keeps leading spaces
        3. markdown Hx    → “[42] ## Title”
        4. generic        → prototype or .name  (+ optional doc-string intro)
        """

        # ── location “box” ────────────────────────────────────────────────
        s = e.metadata.get("start")  # may be None
        e_ = e.metadata.get("end")  # may be None / equal to start

        if s is None:
            loc = "[:]"
        elif e_ is None or e_ == s:
            loc = f"[{s}:]"  # open-ended / single-line
        else:
            loc = f"[{s}:{e_}]"

        # 1️⃣ file header --------------------------------------------------
        if e.type == "file_header":
            kb = e.metadata.get("bytes", 0) / 1024
            return f"{loc} {e.name} ({kb:.2f} kb)"

        # 2️⃣ HTML / outline expander line --------------------------------
        if e.metadata.get("outline_line"):
            return f"{loc} {e.name}"

        # 3️⃣ Markdown headings -------------------------------------------
        if e.type.startswith("heading_h"):
            lvl = int(e.type[-1])  # heading_h3  →  3
            loc = f"[{s}]" if s else "[:]"
            return f"{loc} {'#' * lvl} {e.name}"

        # 4️⃣ generic row --------------------------------------------------
        proto = (e.code.splitlines()[0] if e.code else e.name).strip()

        # prepend doc-string / summary first line, if any
        if e.summary:
            first = e.summary.strip().splitlines()[0]
            first = (first[:77] + "…") if len(first) > 80 else first
            proto = f"{proto}  — {first}"

        return f"{loc} {proto}"

    # ── abstract-mode injection ───────────────────────────────────────
    if prefs.is_abstract_mode_enabled():
        for path, entries in context.state.metadata.items():
            kept = _apply_rollup(entries, path)
            if not kept:
                continue

            # 1️⃣ locate header irrespective of ordering
            header = next((e for e in kept if e.type == "file_header"), kept[0])
            header_line = _render(header)

            # 2️⃣ body – every entry that is *not* the header
            body_lines = "\n".join(
                _render(e) for e in kept if e is not header and e.type != "file_header"
            )

            out.append(f"# metadata: {header_line}\n{body_lines}")

        logger.info(f"Injected metadata for {len(context.state.metadata)} files.")

    # ── raw-mode injection ────────────────────────────────────────────
    else:
        seen: set[str] = set()
        for f in context.state.files:
            if f.path in seen:  # de-dup symlinks
                continue
            seen.add(f.path)
            body = "\n".join(f.lines)
            out.append(f"# file: {f.path} ({len(f.lines)} lines)\n{body}")

        logger.info(f"Injected raw file content for {len(seen)} files.")

    # ── extra files (always raw) ───────────────────────────────────────
    extra_count = 0
    already = {f.path for f in context.state.files}
    for ef in context.state.extra_files:
        if ef.path in already:
            continue
        out.append(f"# file: {ef.path} ({len(ef.lines)} lines)\n{'\n'.join(ef.lines)}")
        extra_count += 1

    if extra_count:
        logger.info(f"Injected {extra_count} extra file(s).")

    return out


def safe_add_extra_context_file(path_str, force=False):
    """
    Adds a file to Olive context by user-facing path (absolute or project-relative).
    Handles ignore rules, file reading, and error messaging.
    Returns True if added, False otherwise.
    """
    from olive.ui import print_error, print_success, print_warning
    from olive.context import context

    root = get_project_root()
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = (root / path).resolve()

    if not path.exists() or not path.is_file():
        print_error(f"{path} does not exist or is not a file.")
        return False

    try:
        rel_path = str(path.relative_to(root))
        path_for_context = rel_path
        outside_root = False
    except ValueError:
        # Path is outside project root
        path_for_context = str(path)
        outside_root = True

    excluded = context.is_file_excluded(path_for_context)
    if excluded and not force:
        print_error(
            f"{path_for_context} is excluded/ignored by your context rules. Use -f to force addition."
        )
        return False
    if excluded and force:
        print_warning(
            f"{path_for_context} is excluded by context rules, but forcibly adding (-f)."
        )
    if outside_root and not force:
        print_error(
            f"{path_for_context} is outside the project root. Use -f to force addition."
        )
        return False
    if outside_root and force:
        print_warning(
            f"{path_for_context} is outside the project root. Forcibly adding (-f)."
        )

    try:
        lines = path.read_text(errors="ignore").splitlines()
    except Exception as e:
        print_error(f"Failed to read {path_for_context}: {e}")
        return False
    try:
        context.add_extra_file(str(path_for_context), lines)
        context.save()
        print_success(f"Added {path_for_context} to context.")
        return True
    except FileExistsError:
        print_error(
            "Refused to add {str(path_for_context)} because this file is already in extra_files."
        )
    return False


def safe_remove_extra_context_file(path_str):
    """
    Removes a file from Olive context by user-facing path (absolute or project-relative).

    Handles appropriate path normalization and user-facing messages.
    Returns True if removed, False otherwise.
    """
    from olive.ui import print_error, print_success, print_info
    from olive.context import context

    root = get_project_root()
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = (root / path).resolve()

    try:
        rel_path = str(path.relative_to(root))
        path_for_context = rel_path
    except ValueError:
        # Path is outside project root
        path_for_context = str(path)

    try:
        count = context.remove_extra_file(str(path_for_context))
        context.save()
        if count == 0:
            print_info(f"{path_for_context} is not in extra context files.")
        else:
            print_success(f"Removed {path_for_context} from context.")
        return True

    except Exception as e:
        print_error(f"Failed to remove {path_for_context}: {e}")
    return False


def get_git_diff_stats():
    try:
        out = subprocess.run(
            ["git", "diff", "--numstat"], capture_output=True, text=True, check=True
        ).stdout
        stats = {}
        for line in out.strip().splitlines():
            added, removed, p = line.split("\t")
            stats[p] = {"added": int(added), "removed": int(removed)}
        return stats
    except Exception:
        return {}
