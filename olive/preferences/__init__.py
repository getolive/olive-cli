# cli/olive/preferences/__init__.py
from typing import Any
from olive import env

import yaml


class Preferences:
    def __init__(self):
        self.prefs: dict = {}
        self.initialized: bool = False
        self._ensure_loaded()  # lazy-load on initial import

    def get_preferences_path(self):
        prefs_path = env.get_dot_olive() / "settings" / "preferences.yml"
        return prefs_path, prefs_path.exists()

    def reload(self):
        """Force a fresh read from disk"""
        self.prefs = self._load_preferences()
        self.initialized = bool(self.prefs)

    def _ensure_loaded(self):
        if not self.initialized:
            self.reload()

    def _load_preferences(self):
        prefs_path, exists = self.get_preferences_path()
        if exists:
            try:
                return yaml.safe_load(prefs_path.read_text()) or {}
            except Exception:
                return {}
        return {}

    def save(self):
        """Write current preferences to ~/.olive/preferences.yml"""
        prefs_path, _ = self.get_preferences_path()
        prefs_path.parent.mkdir(parents=True, exist_ok=True)
        prefs_path.write_text(yaml.safe_dump(self.prefs, default_flow_style=False))

    def get(self, *keys: str, default: Any = None) -> Any:
        self._ensure_loaded()
        result = self.prefs
        for key in keys:
            if not isinstance(result, dict) or key not in result:
                return default
            result = result[key]
        return result

    def set(self, *keys: str, value: Any, save: bool = False):
        """
        Set a value in the nested preferences structure.
        Example: prefs.set("ui", "theme", value="dracula", save=True)
        """
        self._ensure_loaded()
        if not keys:
            raise ValueError("prefs.set() requires at least one key")

        target = self.prefs
        for key in keys[:-1]:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
            target = target[key]
        target[keys[-1]] = value

        if save:
            self.save()

    def is_sandbox_enabled(self) -> bool:
        """with sandbox enabled olive's dispatcher will run commands in the sandbox instead of on the host."""
        if env.is_in_sandbox():
            return False

        return bool(self.get("sandbox", "enabled", default=False))

    def is_abstract_mode_enabled(self) -> bool:
        """in abstract mode olive's context manager will prioritize abstract syntax tree sharing over raw files."""
        return str(
            prefs.get("context", "abstract", "enabled", default=False)
        ).lower() in (
            "1",
            "true",
            "yes",
        )

    def is_voice_enabled(self) -> bool:
        vs = self.get_section("voice", cast="obj")
        _enabled = (
            vs.get("enabled", False)            # dict case
            if isinstance(vs, dict)
            else getattr(vs, "enabled", False)  # model object
        )
        return _enabled and not env.is_in_sandbox()

    def get_section(
        self,
        *keys: str,
        default: Any | None = None,
        cast: str = "dict",
    ):
        """
        Fetch an entire nested section.

        Parameters
        ----------
        *keys
            Hierarchical keys, e.g. ``"voice"`` or ``"ai", "tools"``.
        default
            Fallback if the section is missing (defaults to empty dict).
        cast
            * ``"dict"``  → raw ``dict`` (default)
            * ``"obj"``   → try to instantiate ``<Capitalized>Settings`` from
              ``olive.<top-key>.models`` using Pydantic; falls back to dict if
              the model isn’t found or validation fails.

        Examples
        --------
        >>> prefs.get_section("voice")                # plain dict
        >>> prefs.get_section("voice", cast="obj")    # VoiceSettings object
        """
        data = self.get(*keys, default=default or {})
        if cast == "dict":
            return data or {}

        if cast == "obj":
            import importlib

            top = keys[0] if keys else ""
            try:
                mdl = importlib.import_module(f"olive.{top}.models")
                cls_name = f"{top.capitalize()}Settings"
                cls = getattr(mdl, cls_name)
                return cls.parse_obj(data or {})
            except Exception:
                # graceful fallback – caller still gets a dict
                return data or {}

        raise ValueError(f"Unsupported cast: {cast!r}")


prefs = Preferences()
