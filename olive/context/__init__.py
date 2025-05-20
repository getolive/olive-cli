# cli/olive/context/__init__.py

import fnmatch
import os
import mmap
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Union, List, Dict

# triggers roll-up side-effect registration - intentionally unused.
from olive.context import rollups  # noqa: F401 # pylint: disable=unused-import

from olive.context.models import ASTEntry, ChatMessage, Context, ContextFile
from olive.context.trees import extract_ast_info
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
        return injection.append_context_injection(content)

    def add_extra_file(self, path: str, lines: List):
        """Add a file (by path) to extra_files."""
        norm_path = self._normalize_path(path)
        if any(
            self._normalize_path(f.path) == norm_path for f in self.state.extra_files
        ):
            raise FileExistsError(f"Extra file already exists: {norm_path}")
        self.state.extra_files.append(ContextFile(path=norm_path, lines=lines))

    def remove_extra_file(self, path: str) -> int:
        """Remove a file (by path) to extra_files."""
        norm_path = self._normalize_path(path)
        before = len(self.state.extra_files)
        self.state.extra_files = [
            f
            for f in self.state.extra_files
            if self._normalize_path(f.path) != norm_path
        ]
        return before - len(self.state.extra_files)

    @staticmethod
    def _normalize_path(path: str) -> str:
        return str(Path(path).expanduser().resolve())

    def add_metadata(self, path: str, entries: List[ASTEntry]):
        self.state.metadata[path] = entries

    def add_imports(self, path: str, imports: List[str]):
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

        # 4. Clear AST metadata (if abstract mode disabled)
        if not prefs.is_abstract_mode_enabled():
            self.state.metadata.clear()
            self.state.imports.clear()

        # 5. Summary log
        logger.info(
            f"✅ Hydration complete: "
            f"{len(self.state.system)} system prompt(s), "
            f"{len(self.state.files)} file(s), "
            f"{len(self.state.metadata)} metadata AST maps, "
            f"{len(self.state.imports)} import summaries"
        )

    def _build_context_payload(self) -> List[ContextFile]:
        """
        Build a list of ContextFile objects by reading discovered files.

        This function:
        - Discovers files using preferences
        - Reads up to N lines from each file
        - Skips unreadable files with a warning
        """
        root = get_project_root()
        files = self._discover_files()
        max_lines = prefs.get("context", "max_lines_per_file", default=200)
        abstract_mode = prefs.is_abstract_mode_enabled()

        payload: List[ContextFile] = []
        metadata: Dict[str, List[ASTEntry]] = {}
        imports: Dict[str, List[str]] = {}

        def process(f: Path):
            # ─── Skip obvious binaries (null byte in first 1 KiB) ──────────────────
            try:
                size = f.stat().st_size
                if size:  # mmap needs non-zero length
                    with (
                        f.open("rb") as fh,
                        mmap.mmap(
                            fh.fileno(), min(1024, size), access=mmap.ACCESS_READ
                        ) as mm,
                    ):
                        if b"\x00" in mm:
                            return None  # likely binary; ignore
            except (OSError, ValueError) as e:
                logger.debug(f"Binary sniff failed for {f}: {e}")

            # relative path preferred
            try:
                rel = f.relative_to(root)
                path_str = str(rel)
            except ValueError:
                path_str = str(f)

            try:
                text = f.read_text(errors="ignore")
                lines = text.splitlines()
                cf = ContextFile(path=path_str, lines=lines[:max_lines])

                if abstract_mode:
                    ast_info = extract_ast_info(f)
                    return (
                        cf,
                        path_str,
                        ast_info["entries"],
                        ast_info["summary"].get("imports", []),
                    )
                else:
                    return cf, None, None, None

            except Exception as e:
                logger.warning(f"Failed to read/parse {f}: {e}")
                return None

        workers = min(32, os.cpu_count() or 4)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(process, p) for p in files]
            for fut in as_completed(futures):
                res = fut.result()
                if not res:
                    continue
                cf, m_key, m_entries, m_imports = res
                payload.append(cf)
                if m_key:
                    metadata[m_key] = m_entries
                    imports[m_key] = m_imports

        # push results into state so caller doesn’t need a second pass
        self.state.metadata.update(metadata)
        self.state.imports.update(imports)

        return payload

    def is_file_excluded(self, rel) -> bool:
        exclude_patterns = prefs.get("context", "exclude", "patterns", default=[])
        exclude_paths = set(prefs.get("context", "exclude", "paths", default=[]))
        respect_gitignore = prefs.get("context", "respect_gitignore", default=True)
        rel_str = str(rel)
        rel_parts = Path(rel_str).parts
        # DEBUG: print the paths checked
        logger.debug(f"[DEBUG] is_file_excluded: rel={rel}, rel_str={rel_str}, rel_parts={rel_parts}")
        if "vendor" in rel_parts:
            logger.debug(f"[DEBUG] Excluding {rel_str} due to vendor in path parts")
            return True
        if any(fnmatch.fnmatch(rel_str, pat) for pat in exclude_patterns):
            logger.debug(f"[DEBUG] Excluding {rel_str} due to pattern match")
            return True
        if rel_str in exclude_paths:
            logger.debug(f"[DEBUG] Excluding {rel_str} due to exact path")
            return True
        if respect_gitignore and is_ignored_by_git(rel_str):
            logger.debug(f"[DEBUG] Excluding {rel_str} due to gitignore")
            return True
        return False


    def _discover_files(self, include_extra_files=True) -> List[Path]:
        """
        Discover project source files to include in the Olive context.

        Scans the project root for files matching the configured include patterns,
        while excluding files based on patterns, paths, or `.gitignore` rules
        (depending on preferences). All returned paths are relative to the project root.

        Returns:
            List[Path]: A list of relative file paths to include in the context,
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
            - Extra files are added or skipped based on the value for include_extra_files parameter.
        """
        include_patterns = prefs.get("context", "include", "patterns", default=[])
        include_paths = prefs.get("context", "include", "paths", default=[])
        max_files = prefs.get("context", "max_files", default=10)

        root = get_project_root()
        found: set[Path] = set()
        files_considered = 0

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
                if self.is_file_excluded(rel_path):
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

        # EXTRA: Add extra files from context if requested
        if include_extra_files:
            for cf in self.state.extra_files:
                try:
                    extra_path = Path(cf.path)
                    rel_extra = extra_path.relative_to(root) if extra_path.is_absolute() else Path(cf.path)
                except Exception:
                    rel_extra = Path(cf.path)
                found.add(rel_extra)

        logger.info(
            f"Discovered {len(found)} context files (from {files_considered} scanned)."
        )

        return sorted(found)[:max_files] if max_files >= 0 else sorted(found)

    def hydrate_summary(self) -> str:
        return f"🧠 {len(self.state.files)} files ({len(self.state.extra_files)} extra files) | {len(self.state.chat)} chat | {len(self.state.system)} system"

    def to_dict(self) -> dict:
        return self.state.model_dump()


# ✅ Exported singleton
context = OliveContext()
