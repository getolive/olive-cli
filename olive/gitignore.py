import subprocess
from pathlib import Path

from olive.logger import get_logger

_gitignore_cache = {}
_gitignore_mtime = None

logger = get_logger(__name__)


def is_ignored_by_git(path: str) -> bool:
    global _gitignore_cache, _gitignore_mtime

    gitignore_path = Path(".gitignore")
    if gitignore_path.exists():
        mtime = gitignore_path.stat().st_mtime
        if _gitignore_mtime != mtime:
            _gitignore_cache.clear()
            logger.info("`.gitignore` has changed, cleared ignore cache.")
            _gitignore_mtime = mtime

    if path in _gitignore_cache:
        return _gitignore_cache[path]

    try:
        result = subprocess.run(
            ["git", "check-ignore", path], capture_output=True, text=True
        )
        ignored = result.returncode == 0
        _gitignore_cache[path] = ignored
        if not ignored:
            logger.debug(f"Cached gitignore check: {path} → {ignored}")
        return ignored
    except Exception as e:
        _gitignore_cache[path] = False
        logger.error(f"Failed to run git check-ignore on {path}: {e}")
        return False
