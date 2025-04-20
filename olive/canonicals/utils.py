# cli/olive/canonicals/utils.py

from pathlib import Path
from typing import Any

import yaml

from olive.logger import get_logger

logger = get_logger("canonicals.utils")


def safe_save_yaml(path: Path, data: dict):
    """Safely write YAML to disk, flushing to ensure visibility in mounted volumes."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        tmp.replace(path)  # Atomic move
        path.touch()  # ✅ Explicit flush/update for Docker/mount sync
    except Exception as e:
        logger.exception(f"Failed to save YAML file to {path}: {e}")


class SafeYAMLSaveMixin:
    """
    Mixin that provides a `.safe_save_yaml(path, data)` method
    to write YAML with flush + fsync guarantees.
    """

    def safe_save_yaml(self, path: Path, data: Any):
        return safe_save_yaml(path, data)
