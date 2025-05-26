# cli/olive/canonicals/spec/__init__.py
from pathlib import Path

from olive.logger import get_logger

from . import storage
from . import admin # noqa

logger = get_logger(__name__)


def install():
    """Ensure spec canonical directories and .gitignore rules are in place."""
    import os
    specs_dir = storage.get_specs_dir()
    specs_dir.mkdir(parents=True, exist_ok=True)

    gitignore_path = Path(".gitignore")
    required_lines = [".olive/*"]

    # Only add exception if specs_dir is in the actual repo, not a temp/test dir
    cwd = Path.cwd().resolve()
    specs_dir_resolved = specs_dir.resolve()
    is_temp = any(str(specs_dir_resolved).startswith(p) for p in ["/tmp", "/private/var/folders"])
    # Only add the exception if not in temp and is under repo root
    try:
        is_relative = specs_dir_resolved.is_relative_to(cwd)
    except AttributeError:
        # Python <3.9 fallback
        is_relative = str(specs_dir_resolved).startswith(str(cwd))
    if not is_temp and is_relative:
        required_lines.append(f"!{specs_dir}")

    if gitignore_path.exists():
        lines = set(gitignore_path.read_text().splitlines())
    else:
        lines = set()

    updated = False
    for line in required_lines:
        if line not in lines:
            lines.add(line)
            updated = True

    if updated:
        gitignore_path.write_text("\n".join(sorted(lines)) + "\n")
        logger.info("Updated .gitignore with Olive spec exceptions.")
