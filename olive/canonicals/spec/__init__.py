# cli/olive/canonicals/spec/__init__.py
from pathlib import Path
from olive.logger import get_logger
from . import storage

logger = get_logger(__name__)

def install():
    """Ensure spec canonical directories and .gitignore rules are in place."""
    specs_dir = storage.get_specs_dir()
    specs_dir.mkdir(parents=True, exist_ok=True)

    gitignore_path = Path(".gitignore")
    required_lines = [".olive/*", f"!{specs_dir}"]

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


