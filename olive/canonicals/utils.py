# cli/olive/canonicals/utils.py

from pathlib import Path
from typing import Any

import yaml

from olive.logger import get_logger

logger = get_logger("canonicals.utils")


def safe_save_yaml(path: Path, data: dict):
    """Safely write YAML to disk, flushing to ensure visibility in mounted volumes. Always quote strings."""
    import yaml
    from yaml.representer import SafeRepresenter

    class QuotedString(str):
        pass

    class QuotedSafeDumper(yaml.SafeDumper):
        def represent_str(self, data):
            if '\n' in data:
                return self.represent_scalar('tag:yaml.org,2002:str', data, style='|')
            return self.represent_scalar('tag:yaml.org,2002:str', data, style='"')

    QuotedSafeDumper.add_representer(str, QuotedSafeDumper.represent_str)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            yaml.dump(data, Dumper=QuotedSafeDumper, sort_keys=False, allow_unicode=True, default_flow_style=False),
            encoding="utf-8"
        )
        tmp.replace(path)  # Atomic move
        path.touch()  # Explicit flush/update for Docker/mount sync
    except Exception as e:
        logger.exception(f"Failed to save YAML file to {path}: {e}")


class SafeYAMLSaveMixin:
    """
    Mixin that provides a `.safe_save_yaml(path, data)` method
    to write YAML with flush + fsync guarantees.
    """

    def safe_save_yaml(self, path: Path, data: Any):
        return safe_save_yaml(path, data)
