# cli/olive/context/__init__.py

import fnmatch
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Union

from olive.context.models import ASTEntry, ChatMessage, Context, ContextFile
from olive.context.utils import extract_ast_info, is_abstract_mode_enabled
from olive.env import get_project_root
from olive.gitignore import is_ignored_by_git
from olive.logger import get_logger
from olive.preferences import prefs

from . import injection

logger = get_logger("context")

CONTEXT_PATH = Path(".olive/context/active.json")


class OliveContext:
    """
    Singleton-style procedural interface for Olive's LLM context.
    """

    def __init__(self):
        self.state: Context = self._load()

    def _load(self) -> Context:
        if CONTEXT_PATH.exists():
            try:
                return Context.model_validate_json(CONTEXT_PATH.read_text())
            except Exception as e:
                logger.warning(f"Failed to parse context file — starting fresh: {e}")
        return Context()

    def _hydrate_base_system_prompt(self):
        """
        Ensures the base system prompt (manifesto) is always present as the first entry in self.state.system.
        """
        if self.state.system and self.state.system[0].strip():
            return  # already populated

        system_prompt_path = Path(
            prefs.get(
                "context", "system_prompt_path", default="~/.olive/my_system_prompt.txt"
            )
        ).expanduser()

        if system_prompt_path.exists():
            system_prompt = system_prompt_path.read_text()
            logger.info(f"Loaded system prompt from {system_prompt_path}")
        else:
            logger.warning("Using fallback system prompt.")
            system_prompt = "You are Olive — a local-first, developer-facing, intelligent CLI agent..."

        if self.state.system:
            self.state.system[0] = system_prompt
        else:
            self.state.system = [system_prompt]

    def save(self, max_chat: int = 20):
        self.state.chat = self.state.chat[-max_chat:]
        CONTEXT_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONTEXT_PATH.write_text(self.state.model_dump_json(indent=2))
        logger.info("Context saved.")

    def reset(self):
        self.state = Context()
        self.save()
        logger.info("Context reset.")

    def append_chat(self, role: str, content: str):
        self.state.chat.append(ChatMessage(role=role, content=content))

    def inject_system_message(self, content: Union[str, dict]):
        return injection.append_system_prompt_injection(content)

    def add_file(self, path: str, lines: list[str]):
        self.state.files.append(ContextFile(path=path, lines=lines))

    def add_metadata(self, path: str, entries: list[ASTEntry]):
        self.state.metadata[path] = entries

    def add_imports(self, path: str, imports: list[str]):
        self.state.imports[path] = imports

    def hydrate(self):
        """
        Hydrate files and optionally enrich with AST + imports if abstract mode is enabled.
        """

        # 1. Ensure base system prompt is in place
        self._hydrate_base_system_prompt()

        # 2. Inject additional system messages
        injected = injection.get_context_injections(role="system")
        self.state.system = [self.state.system[0]] + injected

        # 3. Hydrate files
        payload = self._build_context_payload()
        self.state.files = payload

        # 4. Hydrate AST metadata (if abstract mode enabled)
        if is_abstract_mode_enabled():
            for f in payload:
                path = f.path
                try:
                    ast_info = extract_ast_info(path)
                    self.state.metadata[path] = ast_info["entries"]
                    self.state.imports[path] = ast_info["summary"].get("imports", [])
                except Exception as e:
                    logger.warning(f"Failed to parse AST for {path}: {e}")
        else:
            self.state.metadata = {}
            self.state.imports = {}

        # 5. Summary log
        logger.info(
            f"✅ Hydration complete: "
            f"{len(self.state.system)} system prompt(s), "
            f"{len(self.state.files)} file(s), "
            f"{len(self.state.metadata)} metadata AST maps, "
            f"{len(self.state.imports)} import summaries"
        )

    def _build_context_payload(self) -> list[ContextFile]:
        """
        Build a list of ContextFile objects by reading discovered files.

        This function:
        - Discovers files using preferences
        - Reads up to N lines from each file
        - Skips unreadable files with a warning
        """
        files = self._discover_files()
        max_lines = prefs.get("context", "max_lines_per_file", default=200)
        payload = []

        def process(f: Path):
            try:
                lines = f.read_text(errors="ignore").splitlines()
                return ContextFile(path=str(f), lines=lines[:max_lines])
            except Exception as e:
                logger.warning(f"Failed to read file {f}: {e}")
                return None

        with ThreadPoolExecutor(max_workers=os.cpu_count()) as pool:
            for result in pool.map(process, files):
                if result:
                    payload.append(result)

        return payload

    def _discover_files(self) -> list[Path]:
        """
        Discover project source files to include in the Olive context.

        Scans the project root for files matching the configured include patterns,
        while excluding files based on patterns, paths, or `.gitignore` rules
        (depending on preferences). All returned paths are relative to the project root.

        Returns:
            list[Path]: A list of relative file paths to include in the context,
                        ordered deterministically and capped by max_files if set.

        Respects the following preferences:
        - context.include.patterns: filename glob patterns to include (e.g. *.py)
        - context.include.paths: explicit paths to force-include
        - context.exclude.patterns: patterns to exclude
        - context.exclude.paths: specific paths to exclude
        - context.respect_gitignore: whether to exclude files ignored by Git
        - context.max_files: maximum number of files to include (default 10)

        Notes:
            - Only regular files are returned; symlinks and non-files are skipped.
            - Directory traversal excludes common unwanted folders (e.g., .git, __pycache__).
        """
        include_patterns = prefs.get("context", "include", "patterns", default=[])
        include_paths = prefs.get("context", "include", "paths", default=[])
        exclude_patterns = prefs.get("context", "exclude", "patterns", default=[])
        exclude_paths = set(prefs.get("context", "exclude", "paths", default=[]))
        respect_gitignore = prefs.get("context", "respect_gitignore", default=True)
        max_files = prefs.get("context", "max_files", default=10)

        root = get_project_root()
        found: set[Path] = set()
        files_considered = 0

        def is_excluded(rel: Path) -> bool:
            rel_str = str(rel)
            return (
                any(fnmatch.fnmatch(rel_str, pat) for pat in exclude_patterns)
                or rel_str in exclude_paths
                or (respect_gitignore and is_ignored_by_git(rel_str))
            )

        # Common directories to skip entirely
        ignored_dirs = {".git", "__pycache__", ".venv", "node_modules", ".olive"}

        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            # Prune directories in-place to avoid descending into unwanted ones
            dirnames[:] = [d for d in dirnames if d not in ignored_dirs]

            for fname in filenames:
                fpath = Path(dirpath) / fname
                rel_path = fpath.relative_to(root)

                if not fpath.is_file():
                    continue
                if not any(
                    fnmatch.fnmatch(fpath.name, pat) for pat in include_patterns
                ):
                    continue
                if is_excluded(rel_path):
                    continue

                found.add(rel_path)
                files_considered += 1
                if 0 <= max_files <= len(found):
                    break
            if 0 <= max_files <= len(found):
                break

        # Explicit includes (e.g., specific config files)
        for p in include_paths:
            explicit = root / p
            if explicit.exists() and explicit.is_file():
                found.add(explicit.relative_to(root))

        logger.info(
            f"Discovered {len(found)} context files (from {files_considered} scanned)."
        )
        return sorted(found)[:max_files] if max_files >= 0 else sorted(found)

    def hydrate_summary(self) -> str:
        return f"🧠 {len(self.state.files)} files | {len(self.state.chat)} chat | {len(self.state.system)} system"

    def to_dict(self) -> dict:
        return self.state.model_dump()


# ✅ Exported singleton
context = OliveContext()
