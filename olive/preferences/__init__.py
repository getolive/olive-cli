# cli/olive/preferences/__init__.py
from typing import Any
from olive import env

import yaml


class Preferences:
    def __init__(self):
        self.prefs: dict = {}
        self.initialized: bool = False
        self._ensure_loaded() # lazy-load on initial import

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

    def pretty_summary(self):
        """Returns a structured dict of preferences organized by section"""
        return {
            "⚙️ Context Settings": [
                (
                    "context.include.patterns",
                    self.get("context", "include", "patterns"),
                ),
                ("context.include.paths", self.get("context", "include", "paths")),
                (
                    "context.exclude.patterns",
                    self.get("context", "exclude", "patterns"),
                ),
                ("context.exclude.paths", self.get("context", "exclude", "paths")),
                ("context.max_files", self.get("context", "max_files")),
                (
                    "context.max_lines_per_file",
                    self.get("context", "max_lines_per_file"),
                ),
                ("context.max_tokens", self.get("context", "max_tokens")),
                ("context.respect_gitignore", self.get("context", "respect_gitignore")),
                (
                    "context.system_prompt_path",
                    self.get("context", "system_prompt_path"),
                ),
            ],
            "🧠 AI Settings": [
                ("ai.model", self.get("ai", "model")),
                ("ai.provider", self.get("ai", "provider")),
                ("ai.temperature", self.get("ai", "temperature")),
                ("ai.base_url", self.get("ai", "base_url")),
            ],
            "🔧 AI Tools": [
                ("ai.tools.mode", self.get("ai", "tools", "mode")),
                ("ai.tools.whitelist", self.get("ai", "tools", "whitelist")),
                ("ai.tools.blacklist", self.get("ai", "tools", "blacklist")),
            ],
            "🧰 Builder Mode": [
                ("builder_mode.autonomy", self.get("builder_mode", "autonomy")),
                (
                    "builder_mode.confidence_threshold",
                    self.get("builder_mode", "confidence_threshold"),
                ),
                ("builder_mode.prompt_path", self.get("builder_mode", "prompt_path")),
            ],
            "🚨 Code Smells": [
                ("code_smells.enabled", self.get("code_smells", "enabled")),
                ("code_smells.linters", self.get("code_smells", "linters")),
                (
                    "code_smells.flags.consistent_formatting",
                    self.get("code_smells", "flags", "consistent_formatting"),
                ),
                (
                    "code_smells.flags.enforce_type_hints",
                    self.get("code_smells", "flags", "enforce_type_hints"),
                ),
                (
                    "code_smells.flags.no_todo_comments",
                    self.get("code_smells", "flags", "no_todo_comments"),
                ),
            ],
            "🖥️ UI": [
                ("ui.prompt", self.get("ui", "prompt")),
            ],
            "📊 LLM Settings": [
                ("llm.model", self.get("llm", "model")),
                ("llm.temperature", self.get("llm", "temperature")),
                ("llm.api_base", self.get("llm", "api_base")),
            ],
            "🔒 Other": [
                ("sandbox.enabled", self.get("sandbox", "enabled")),
            ],
        }


prefs = Preferences()
