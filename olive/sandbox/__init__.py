"""
olive.sandbox
=============

Lean orchestrator that builds and manages Olive’s Docker sandbox.

All filesystem, session and “inside-sandbox?” logic flows through *olive.env*.
"""

from __future__ import annotations

import os
import json
import shutil
import hashlib
import subprocess
from pathlib import Path
from typing import Optional
from functools import cached_property
from tempfile import NamedTemporaryFile
from importlib import metadata, resources

from olive import env  # single source-of-truth helpers
from olive.logger import get_logger
from olive.preferences import prefs
from olive.tasks.models import TaskSpec
from .utils import docker_ready, get_container_name

logger = get_logger("sandbox")

# ───────────────────────── constants ──────────────────────────

IMAGE_TAG = "olive-sandbox"
NOSESSION_CONTAINER_NAME = "olive-sandbox"

# wheel staging lives *inside* the sandbox dir
def _user_wheel_cache_dir() -> Path:
    _user_wheel_cache_root = env.get_user_root() / "wheels"
    if not _user_wheel_cache_root.exists():
        _user_wheel_cache_root.mkdir(parents=True, exist_ok=True)
    return _user_wheel_cache_root

def _sandbox_dir() -> Path:
    return env.get_sandbox_root()

def _dockerfile_path() -> Path:
    return _sandbox_dir() / "Dockerfile"


def _stage_dir() -> Path:
    return _sandbox_dir() / ".build"


def _cache_path() -> Path:
    return _sandbox_dir() / ".sandbox_state.json"


# ───────────────────────── utils ──────────────────────────────
def _sh(cmd: list[str], *, capture: bool = False, cwd: Path | None = None) -> str:
    if capture:
        return subprocess.check_output(
            cmd, cwd=cwd, text=True, stderr=subprocess.STDOUT
        ).strip()
    subprocess.check_call(cmd, cwd=cwd)
    return ""


def _settings_digest() -> str:
    _settings_dir = env.get_dot_olive_settings()
    h = hashlib.sha256()
    for p in sorted(_settings_dir.iterdir()) if _settings_dir.exists() else []:
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()[:12]


def _extra_apt_packages() -> list[str]:
    """extra packages to apt-get into the sandbox (can be missing/null/none)"""
    return prefs.get("sandbox", "environment", "extra_apt_packages", default=[]) or []


def _disk_mode() -> str:
    """mount or copy, default: mount"""
    return prefs.get("sandbox", "disk", default="mount")


# ──────────────── ensure Dockerfile + entrypoint exist ────────────────
def _ensure_docker_assets() -> None:
    """Copy Dockerfile and entrypoint.sh from the Olive package into the project."""
    _sandbox_root = _sandbox_dir()
    _sandbox_root.mkdir(parents=True, exist_ok=True)
    for asset in ("Dockerfile", "entrypoint.sh"):
        src = resources.files("olive.sandbox").joinpath(asset)
        dst = _sandbox_root / asset
        # copy only if missing or source is newer
        if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
            shutil.copy2(src, dst)


import importlib.resources as import_resources
import importlib.metadata as import_metadata

# ───────────────── locate olive sources ───────────────────────
def _olive_source_path() -> Optional[Path]:
    """
    Locate the *source* root of Olive – the directory that owns ``pyproject.toml``.

    Strategy (stop at first hit):

    1. ``$OLIVE_SOURCE_PATH``                      – explicit > implicit.
    2. Walk parents of ``Path(__file__)``          – editable install or in-repo run.
    3. ``importlib.resources.files(__package__)``  – PEP 302/451 canonical origin.
    4. Inspect the *distribution* (``*.dist-info``) – allows recovery even from
       a wheel *if* the wheel includes ``pyproject.toml``.
    5. Fallback: ``None`` so caller can decide (e.g. raise, warn, clone repo).

    Returns
    -------
    pathlib.Path | None
        Absolute path to the directory that contains ``pyproject.toml``, or
        ``None`` if it cannot be located with high confidence.
    """
    # 1 ────────────────────────────────────────────────────────────────────────
    env = os.getenv("OLIVE_SOURCE_PATH")
    if env:
        p = Path(env).expanduser().resolve()
        if (p / "pyproject.toml").is_file():
            return p

    # helper: climb until a sentinel file is found
    def _find_in_parents(start: Path, sentinel: str) -> Optional[Path]:
        for parent in start.resolve().parents:
            if (parent / sentinel).is_file():
                return parent
        return None

    # 2 ────────────────────────────────────────────────────────────────────────
    here_based = _find_in_parents(Path(__file__), "pyproject.toml")
    if here_based:
        return here_based

    # 3 ────────────────────────────────────────────────────────────────────────
    try:
        pkg_root = import_resources.files(__package__).resolve()
        resource_based = _find_in_parents(pkg_root, "pyproject.toml")
        if resource_based:
            return resource_based
    except ModuleNotFoundError:  # very unlikely, but play safe
        pass

    # 4 ────────────────────────────────────────────────────────────────────────
    for dist_name in ("olive-cli", "olive"):
        try:
            dist = import_metadata.distribution(dist_name)
        except import_metadata.PackageNotFoundError:
            continue

        base = Path(dist.locate_file("")).resolve()
        dist_based = _find_in_parents(base, "pyproject.toml")
        if dist_based:
            return dist_based

        # Wheel did not ship pyproject.toml – search RECORD for it (rare but legal)
        record_path = dist.locate_file("RECORD")
        if record_path.is_file():
            with record_path.open(encoding="utf-8") as fh:
                for line in fh:
                    fpath = line.split(",", 1)[0]
                    if fpath.endswith("pyproject.toml"):
                        return Path(dist.locate_file(fpath)).parent

    # 5 ────────────────────────────────────────────────────────────────────────
    return None



# ───────────────── wheel builder / stager ─────────────────────
def _olive_version() -> str:
    try:
        return metadata.version("olive")
    except metadata.PackageNotFoundError:
        return "unknown"


def _cleanup_stage() -> None:
    _stage_root = _stage_dir()
    if _stage_root.exists():
        for p in _stage_root.iterdir():
            p.unlink(missing_ok=True)


# ------- wheel helpers (single implementation) -----------------------
def _cached_wheels(version: str) -> list[Path]:
    return list(
        (_user_wheel_cache_dir() / f"olive-{version}-*.whl").parent.glob(
            f"olive-{version}-*.whl"
        )
    )


def _build_wheel_into_cache(version: str, source: Path) -> Path:
    print(f"[sandbox] Building Olive {version} wheel from {source} …")
    before = set(_cached_wheels(version))
    _sh(["uv", "build", "--wheel", "--out-dir", str(_user_wheel_cache_dir())], cwd=source)
    after = set(_cached_wheels(version))
    new = list(after - before)
    if not new:
        raise RuntimeError("uv build completed but no wheel found in cache.")
    return new[0]


def _stage(wheel: Path) -> Path:
    """
    Place the wheel *inside* the Docker build-context.

    •  If the wheel already lives under the project root, a symlink is fine.
    •  Otherwise we *must* copy, because Docker disallows context escapes.
    """
    _stage_root = _stage_dir()
    _stage_root.mkdir(parents=True, exist_ok=True)
    target = _stage_root / wheel.name

    if target.exists():  # already staged
        return target

    try:
        wheel.relative_to(env.get_project_root())  # inside context? -> symlink
        target.symlink_to(wheel)
    except (ValueError, OSError):
        shutil.copy2(wheel, target)  # outside context -> hard copy

    return target


def _ensure_staged_wheel() -> Path:
    """Return wheel path inside build context; build & stage if needed."""
    ver = _olive_version()
    src = _olive_source_path() or env.get_project_root()

    cached = _cached_wheels(ver) if ver != "unknown" else []
    if not cached:
        # Always (re)build when version unknown or cache empty
        built = _build_wheel_into_cache(ver, src)
        cached = [built]

    wheel = max(cached, key=lambda p: p.stat().st_mtime)
    return _stage(wheel)


# ───────────────── state helpers ──────────────────────────────
def _load_state() -> dict:
    return json.loads(_cache_path().read_text()) if _cache_path().exists() else {}


def _save_state(data: dict) -> None:
    _cache_path().parent.mkdir(parents=True, exist_ok=True)
    _cache_path().write_text(json.dumps(data))


def _build_container_name() -> str:
    sid = env.get_session_id()
    if not sid:
        raise RuntimeError(
            "Shell session not initialized – call initialize_shell_session() first"
        )
    return get_container_name()


# ───────────────── sandbox singleton ──────────────────────────
class _Sandbox:
    _instance: Optional["_Sandbox"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @cached_property
    def container_name(self) -> str:  # type: ignore[override]
        return _build_container_name()

    # ----------------------- build ----------------------------
    @docker_ready
    def build(self, *, force: bool = False) -> None:
        _ensure_docker_assets()

        wheel_path = _ensure_staged_wheel()
        wheel_hash = hashlib.sha256(wheel_path.read_bytes()).hexdigest()[:12]

        stamp = {
            "pref_hash": _settings_digest(),  # settings/ files
            "olive_ver": _olive_version(),  # version string
            "wheel_hash": wheel_hash,  # exact byte-hash
            "extra_apt": ",".join(_extra_apt_packages()),  # apt add-ons
        }

        image_exists = bool(_sh(["docker", "images", "-q", IMAGE_TAG], capture=True))
        if image_exists and not force and stamp == _load_state():
            print("✓ sandbox image up-to-date")
            return

        print(f"[sandbox] Staged wheel {wheel_path.name}  sha={wheel_hash}")

        try:
            _sh(
                [
                    "docker",
                    "build",
                    *(["--progress=plain"] if os.getenv("CI") else []),
                    "-t",
                    IMAGE_TAG,
                    "-f",
                    str(_dockerfile_path()),
                    "--build-arg",
                    f"EXTRA_APT={stamp['extra_apt']}",
                    "--build-arg",
                    "PLAYWRIGHT_VERSION=1.52.0",
                    str(env.get_project_root()),
                ]
            )
            _save_state(stamp)
            print("✓ build complete")
        finally:
            _cleanup_stage()

    # ----------------------- lifecycle ------------------------
    @docker_ready
    def start(self, force_build: bool = False) -> None:
        self.build(force=force_build)
        if self.is_running():
            print("sandbox already running")
            return

        mount = (
            f"type=bind,src={env.get_project_root()},dst=/mnt/project"
            if _disk_mode() == "mount"
            else "type=volume,dst=/mnt/project"
        )

        sid = env.get_session_id()

        cid = _sh(
            [
                "docker",
                "run",
                "-dit",
                "--name",
                self.container_name,
                "--mount",
                mount,
                "-e",
                "CI=true",
                "-e",
                f"OLIVE_SESSION_ID={sid}",  # propagage session to match up container & host
                IMAGE_TAG,
            ],
            capture=True,
        )
        print(f"[sandbox] started {cid[:12]} {self.container_name}")

    @docker_ready
    def stop(self) -> None:
        if self.is_running():
            _sh(["docker", "rm", "-f", self.container_name])
            print("[sandbox] stopped")

    def restart(self) -> None:
        self.stop()
        self.start()

    # ----------------------- info -----------------------------
    def is_running(self) -> bool:
        try:
            return bool(
                _sh(["docker", "ps", "-q", "-f",
                     f"name={self.container_name}"], capture=True)
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            # daemon unreachable or CLI vanished → treat as “not running”
            return False

    

    def logs(self, *, tail: int = 120, follow: bool = False) -> None:
        if not self.is_running():
            raise RuntimeError("Sandbox not running.")
        cmd = ["docker", "logs", f"--tail={tail}"]
        if follow:
            cmd.append("--follow")
        cmd.append(self.container_name)
        subprocess.run(cmd, check=False)

    def status(self) -> str:
        if not self.is_running():
            return "stopped"
        return _sh(
            ["docker", "inspect", "-f", "{{.State.Status}}", self.container_name],
            capture=True,
        )

    # ───────────────────────── task dispatch ─────────────────────────
    def dispatch_task(self, spec: TaskSpec, wait: bool = True) -> dict:
        """
        Serialize *spec* into the shared RPC directory, then ask the running
        container to execute it via `olive run-task <json>`.

        The function blocks until a result-file appears **unless** `wait=False`
        or *spec.return_id* is *None*.
        """
        if not self.is_running():
            raise RuntimeError("Sandbox must be running before dispatching tasks")

        sid = env.get_session_id()
        if not sid:
            raise RuntimeError("dispatch_task outside sandbox session")

        # --- write task file atomically -------------------------------------
        rpc_dir = env.get_sandbox_rpc_dir()  # ensures dir
        task_path = env.get_task_file(spec.return_id or spec.id)
        tmp: Path | None = None
        try:
            with NamedTemporaryFile("w", dir=rpc_dir, delete=False, suffix=".tmp") as f:
                json.dump(spec.model_dump(), f, indent=2)
                f.flush()
                os.fsync(f.fileno())
                tmp = Path(f.name)
            tmp.rename(task_path)
        finally:
            if tmp and tmp.exists():
                tmp.unlink(missing_ok=True)

        # --- tell the container to run it -----------------------------------
        inside_json = Path("/mnt/project") / task_path.relative_to(
            env.get_project_root()
        )
        _sh(
            [
                "docker",
                "exec",
                "-w",
                "/mnt/project",
                self.container_name,
                "olive",
                "run-task",
                str(inside_json),
            ],
            capture=True,
        )

        if not wait or spec.return_id is None:
            return {"dispatched": True}

        # --- wait for result file -------------------------------------------
        result_path = env.get_result_file(spec.return_id or spec.id)
        from olive.tasks.watcher import wait_file  # lazy import

        wait_file(result_path, timeout=None)
        return json.loads(result_path.read_text())


# Public singleton
sandbox = _Sandbox()
