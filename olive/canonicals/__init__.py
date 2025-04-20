# cli/olive/canonicals/__init__.py
import importlib
import pkgutil
from pathlib import Path
from typing import Dict

from olive.logger import get_logger

from .models import Canonical

logger = get_logger("canonicals")


class CanonicalRegistry:
    """Registry and loader for all canonical modules in Olive."""

    def __init__(self, package_root: str = "olive.canonicals"):
        self.package_root = package_root
        self.available: Dict[str, Canonical] = {}

    def discover_all(self, install: bool = True):
        """Discover and optionally install all canonicals under the package root."""
        base_path = Path(__file__).parent

        for _, name, ispkg in pkgutil.iter_modules([str(base_path)]):
            if not ispkg:
                logger.debug(f"Skipping non-package in canonicals/: {name}")
                continue

            mod_name = f"{self.package_root}.{name}"
            installed = False
            message = ""

            try:
                mod = importlib.import_module(mod_name)

                if hasattr(mod, "install") and callable(mod.install):
                    if install:
                        mod.install()
                        message = "Installed successfully."
                        logger.info(f"{name}: {message}")
                    else:
                        message = "Install available but skipped."
                        logger.debug(f"{name}: {message}")
                    installed = True
                else:
                    message = "No install() function found."
                    logger.debug(f"{name}: {message}")

            except Exception as e:
                message = f"Failed to load {mod_name}: {e}"
                logger.warning(f"{name}: {message}")

            self.available[name] = Canonical(
                name=name, installed=installed, message=message
            )

    def list(self) -> Dict[str, Canonical]:
        """Return dictionary of discovered canonicals."""
        return self.available


# Export singleton
canonicals_registry = CanonicalRegistry()
