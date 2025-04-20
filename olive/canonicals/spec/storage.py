# cli/olive/canonicals/spec/storage.py
from pathlib import Path
from typing import List

import yaml

from olive.env import get_project_root
from olive.logger import get_logger

from .models import FeatureSpec

logger = get_logger(__name__)


def get_all_specs() -> List[FeatureSpec]:
    """Load all valid specs from the specs directory, skipping non-spec files."""
    specs = []
    for path in sorted(get_specs_dir().glob("*.yml")):
        if path.name == "manifest.yml":
            continue  # Skip non-spec file

        try:
            data = yaml.safe_load(path.read_text())
            # Validate structure (won't raise if minimal fields exist)
            FeatureSpec.model_validate(data)  # raises ValidationError if invalid
            specs.append(FeatureSpec(**data))
        except Exception as e:
            logger.debug(f"Skipped invalid spec file {path}: {e}")
    return specs


def get_specs_dir() -> Path:
    """The olive path where specs are stored"""
    return get_project_root() / ".olive/specs/"
