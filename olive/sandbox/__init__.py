"""
olive.sandbox.__init__  – final draft
=====================================

High‑level management of the Olive Docker sandbox.

All filesystem locations, session‑IDs and env‑vars are routed through
:pyMod:`olive.env` so the exact same code runs on the host *and* inside the
container.
"""

from __future__ import annotations

import asyncio
import atexit
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import tarfile
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from enum import Enum, auto

from rich.errors import LiveError
from rich.markup import escape

from olive import env
from olive.logger import get_logger
from olive.preferences import prefs
from olive.tasks.models import TaskSpec
from olive.ui import console, console_lock, print_warning

from olive.sandbox.utils import docker_required, get_container_name, get_mounts

logger = get_logger("sandbox")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


# ──────────────────────────────────────────────────────────────
# Helper: Rich spinner that never explodes
# ──────────────────────────────────────────────────────────────
@contextmanager
def _safe_status(msg: str):
    try:
        with console.status(f"[highlight]{msg}[/highlight]", spinner="dots") as st:
            yield st
    except LiveError:
        # Already inside a live display – fall back to plain text
        print(f"[dim]{msg} …[/dim]")
        yield console


class BuildBackend(Enum):
    """What toolchain will actually build container images for us?"""

    DOCKER_BUILDX = auto()  # Docker CLI + Buildx extension available
    PODMAN = auto()  # podman is aliased to `docker`; Buildx disabled
    NONE = auto()  # sandbox disabled or Buildx unavailable


@docker_required
def ensure_build_backend() -> BuildBackend:
    """
    Verify we have *some* image-building backend and prepare it if needed.

    Returns
    -------
    BuildBackend
        • DOCKER_BUILDX if Docker Buildx is ready (creates `olive-builder` on first run)
        • PODMAN        if `docker` is really a Podman alias ⇒ skip Buildx flags
        • NONE          if sandbox is disabled in preferences
    """
    if not prefs.is_sandbox_enabled():
        return BuildBackend.NONE

    docker_path = shutil.which("docker")
    if not docker_path:
        raise RuntimeError(
            "`docker` CLI not found – install Docker/Podman or disable the sandbox."
        )

    # Detect Podman masquerading as docker (common: `alias docker=podman`)
    docker_real = os.path.realpath(docker_path)
    if "podman" in docker_real.lower():
        logger.info("Detected Podman alias – Buildx will be skipped.")
        return BuildBackend.PODMAN

    # 1.  Ensure the Buildx sub-command itself exists
    if (
        subprocess.run(["docker", "buildx", "version"], capture_output=True).returncode
        != 0
    ):
        raise RuntimeError("Docker Buildx is unavailable (Docker ≥ 20.10 required).")

    # 2.  Is there already an active builder?
    inspect = subprocess.run(
        ["docker", "buildx", "inspect"], capture_output=True, text=True
    )
    if inspect.returncode == 0 and "Driver:" in inspect.stdout:
        return BuildBackend.DOCKER_BUILDX  # all good, nothing to do

    # 3.  We need to create a builder (first run)
    ctx_vsp: Path = env.get_project_root() / ".venv"
    if not ctx_vsp.exists():
        raise RuntimeError(".venv missing from build context – check .dockerignore")

    try:
        subprocess.check_call(
            [
                "docker",
                "buildx",
                "create",
                "--name",
                "olive-builder",
                "--driver",
                "docker-container",
                "--bootstrap",
                "--use",
            ]
        )
        logger.info("Created and bootstrapped Docker Buildx builder 'olive-builder'.")
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Failed to create Buildx builder: {exc}") from exc

    return BuildBackend.DOCKER_BUILDX


# ──────────────────────────────────────────────────────────────
# Sandbox manager
# ──────────────────────────────────────────────────────────────
class SandboxManager:
    def __init__(self) -> None:
        self.container_name: str | None = None
        self.log_path: Path = env.get_logs_root() / "sandbox.log"  # ensures dir
        _ = ensure_build_backend()  # builder ready

    # ────────────────────────────────────────────── build phase
    def write_dockerignore(self) -> None:
        sbx_root = env.get_sandbox_root()
        proj_root = env.get_project_root()
        snapshot_dir = sbx_root / ".olive-snapshot"
        sbx_ignore = sbx_root / ".dockerignore"
        proj_ignore = proj_root / ".dockerignore"

        logger.info("Writing .dockerignore → %s", sbx_ignore)
        sbx_root.mkdir(parents=True, exist_ok=True)

        def _rel(p: Path) -> str:
            return str(p.relative_to(proj_root))

        header = [
            "# Generated by Olive",
            f"# {_dt.datetime.now():%Y-%m-%d %H:%M:%S}",
            "# Auto‑generated – DO NOT EDIT\n",
        ]

        base_ignores = [
            "*.db",
            "*.log",
            "*.pyc",
            "*.sqlite3",
            ".DS_Store",
            ".env",
            ".git/",
            ".git/**/*",
            ".venv/",
            ".venv/**.*",
            "__pycache__/",
            "node_modules/",
            ".olive/",
            ".olive/run/",
        ]

        allow = [
            "!.venv/lib/*/site-packages/**",
            f"!{_rel(snapshot_dir)}",
            f"!{_rel(sbx_root / 'staging')}",
            f"!{_rel(sbx_root / 'staging' / 'olive')}/**",
            "!.olive/sandbox/entrypoint.sh",
        ]

        extra = prefs.get("context", "exclude", "paths", default=[]) + prefs.get(
            "context", "exclude", "patterns", default=[]
        )

        sbx_ignore.write_text(
            "\n".join(header + sorted(set(base_ignores)) + allow + sorted(extra)) + "\n"
        )
        shutil.copyfile(sbx_ignore, proj_ignore)

    @docker_required
    def build(self, *, force: bool = False) -> None:
        """
        Rebuild the sandbox image when `_auto_refresh()` detects staleness
        or when `force=True`.

        Snapshot source: project `.olive/` minus its `sandbox/` subtree
        (prevents infinite `.olive-snapshot/sandbox/.olive-snapshot…`).
        Olive package is staged at /olive, project root becomes /mnt/project.
        """
        # ── quick-out if nothing changed ───────────────────────────────
        self.write_dockerignore()
        backend: BuildBackend = ensure_build_backend()

        if backend is BuildBackend.NONE:
            logger.info("Sandbox disabled – skipping image build.")
            return

        refresh_required = self._auto_refresh() or force
        if not refresh_required:
            logger.info("Sandbox image is current – skipping rebuild.")
            return

        # ── paths & snapshot bookkeeping (unchanged) ─────────────────────
        proj_root = env.get_project_root()
        dot_olive = env.get_dot_olive()  # project-local .olive
        sbx_root = env.get_sandbox_root()
        snapshot = sbx_root / ".olive-snapshot"
        marker = snapshot / ".snapshot_hash"
        backup_dir = sbx_root / "old_snapshots"
        backup_dir.mkdir(exist_ok=True)

        comp_hash = self._snapshot_hash()  # includes prefs/prompts
        image_tag = f"olive/sandbox:{comp_hash[:12]}"

        # ── stage Olive LIB source ( /olive ) ──────────────────────────
        olive_proj = env.get_resource_path("olive")
        olive_stage = sbx_root / "staging" / "olive"
        olive_hash = self._hash_directory(olive_proj)
        olive_hashf = sbx_root / ".olive_src_hash"

        if (not olive_stage.exists()) or (
            olive_hashf.read_text() if olive_hashf.exists() else ""
        ) != olive_hash:
            if olive_stage.exists():
                shutil.rmtree(olive_stage)
            shutil.copytree(olive_proj, olive_stage, symlinks=False)
            olive_hashf.write_text(olive_hash)

        # ── snapshot project .olive WITHOUT its sandbox dir ──────────────
        if snapshot.exists():
            ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            with tarfile.open(backup_dir / f"snapshot_{ts}.tar.gz", "w:gz") as tar:
                tar.add(snapshot, arcname=".olive-snapshot")
            shutil.rmtree(snapshot)

        def _ignore(d: str, names: list[str]) -> set[str]:
            # Skip top-level .olive/sandbox only
            return {"sandbox"} if Path(d).samefile(dot_olive) else set()

        shutil.copytree(dot_olive, snapshot, ignore=_ignore)
        self._disable_sandbox(snapshot / "preferences.yml")
        marker.write_text(comp_hash)

        # ── render Dockerfile if needed ──────────────────────────────────
        tmpl = env.get_resource_path("olive.sandbox", "Dockerfile.template")
        dockerfile = sbx_root / "Dockerfile"
        rendered = self._render_dockerfile(tmpl)

        if not dockerfile.exists() or dockerfile.read_text() != rendered:
            dockerfile.write_text(rendered)
            shutil.copy(
                env.get_resource_path("olive.sandbox", "entrypoint.sh"),
                sbx_root / "entrypoint.sh",
            )
            logger.info("Dockerfile refreshed.")

        # ── choose build command for backend ─────────────────────────────
        if backend is BuildBackend.DOCKER_BUILDX:
            cmd = [
                "docker",
                "buildx",
                "build",
                "--load",
                "--cache-to",
                "type=inline",
                "--cache-from",
                "type=inline",
            ]
            env_vars = {**os.environ, "DOCKER_BUILDKIT": "1"}
        elif backend is BuildBackend.PODMAN:  # Buildx unavailable
            cmd = ["docker", "build"]  # alias → podman
            env_vars = os.environ.copy()
        else:  # just in case
            raise RuntimeError(f"Unsupported build backend: {backend!r}")

        # tags and context are common to all backends
        cmd += [
            "-t",
            image_tag,
            "-t",
            "olive/sandbox:latest",
            "-f",
            str(dockerfile),
            str(proj_root),
        ]

        # ── build & stream logs ──────────────────────────────────────────
        with _safe_status("Building sandbox image…") as st:
            proc = subprocess.Popen(  # noqa: S603
                cmd,
                env=env_vars,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
            )
            assert proc.stdout  # for mypy
            for ln in proc.stdout:
                msg = ANSI_RE.sub("", ln).rstrip()
                if msg:
                    logger.debug("[build] %s", msg)
                    with console_lock():
                        st.update(f"[secondary]{escape(msg[:80])}[/secondary]")
            proc.wait()

        if proc.returncode:
            raise RuntimeError("Container build failed – see log for details.")
        logger.info("✅ Sandbox image built → %s", image_tag)

    # ────────────────────────────────────────────── lifecycle
    @docker_required
    def start(self) -> None:
        if self.is_running():
            logger.info("Sandbox already running.")
            return

        if self._auto_refresh():
            print_warning("Sandbox config changed --> rebuilding image...")
            self.build()
        else:
            self._ensure_image()

        sid = env.get_session_id() or env.generate_session_id()
        sbx_root = env.get_sandbox_run_root()  # also creates RPC/result dirs
        os.environ["OLIVE_SANDBOX_DIR"] = str(sbx_root)

        self.container_name = get_container_name()

        mode = os.getenv("SANDBOX_MODE") or prefs.get("sandbox", "disk", default="copy")
        mnt_args: list[str] = []
        if mode == "mount":
            for host, cont, ro in get_mounts():
                mnt_args += ["-v", f"{host}:{cont}:{'ro' if ro else 'rw'}"]
        elif mode == "copy":
            logger.info("Sandbox running in COPY mode.")
        else:
            logger.warning("Unknown SANDBOX_MODE=%s (defaulting to COPY)", mode)

        cmd = [
            "docker",
            "run",
            "-dit",
            "--name",
            self.container_name,
            "-e",
            "IS_OLIVE_SANDBOX=1",
            "-e",
            f"OLIVE_SESSION_ID={sid}",
            "-e",
            f"OLIVE_SANDBOX_DIR=/mnt/project/.olive/run/sbx/{sid}",
            *mnt_args,
            "--workdir",
            "/mnt/project",
            "olive/sandbox:latest",
            "daemon",
        ]

        with _safe_status("Starting sandbox…") as st:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )  # noqa: S603
            assert proc.stdout
            for line in proc.stdout:
                clean = ANSI_RE.sub("", line).strip()
                if clean:
                    logger.debug("[docker run] %s", clean)
                    with console_lock():
                        st.update(f"[secondary]{escape(clean[:80])}[/secondary]")
            proc.wait()

        if proc.returncode:
            raise subprocess.CalledProcessError(proc.returncode, cmd)
        if not self.is_running():
            raise RuntimeError("Sandbox container exited immediately.")
        logger.info("✅ Sandbox container is running.")

    @docker_required
    def stop(self) -> None:
        if not self.is_running():
            return
        logger.info("Stopping sandbox container: %s", self.container_name)
        subprocess.run(
            ["docker", "rm", "-f", self.container_name], stdout=subprocess.DEVNULL
        )
        logger.info("Sandbox stopped.")

    def restart(self) -> None:
        self.stop()
        self.start()

    # ────────────────────────────────────────────── admin
    @docker_required
    def status(self) -> dict:
        if not self.is_running():
            return {"running": False}
        res = subprocess.run(
            [
                "docker",
                "stats",
                "--no-stream",
                "--format",
                "{{.Name}} {{.CPUPerc}} {{.MemUsage}}",
            ],
            capture_output=True,
            text=True,
        )
        for line in res.stdout.strip().splitlines():
            if line.startswith(self.container_name):
                _, cpu, mem = line.split(maxsplit=2)
                return {
                    "running": True,
                    "cpu": cpu,
                    "mem": mem,
                    "name": self.container_name,
                }
        return {"running": True, "name": self.container_name}

    @docker_required
    def logs(self, *, tail: int = 40, follow: bool = False) -> None:
        if not self.is_running():
            print("[yellow]Sandbox is not running.[/yellow]")
            return
        cmd = ["docker", "logs", "--tail", str(tail)]
        if follow:
            cmd.append("--follow")
        cmd.append(self.container_name)
        subprocess.run(cmd)

    # ────────────────────────────────────────────── dispatch
    @docker_required
    def dispatch_task(self, spec: TaskSpec, *, wait: bool = True) -> dict:
        sid = env.get_session_id()
        if not sid:
            raise RuntimeError("dispatch_task called outside sandbox session")

        rpc_dir = env.get_sandbox_rpc_dir()

        result_filename = spec.return_id or spec.id
        task_path = env.get_task_file(result_filename)

        # atomic write
        tmp: Path | None = None
        try:
            with NamedTemporaryFile("w", dir=rpc_dir, delete=False, suffix=".tmp") as t:
                json.dump(spec.model_dump(), t, indent=2)
                t.flush()
                os.fsync(t.fileno())
                tmp = Path(t.name)
            tmp.rename(task_path)
        finally:
            if tmp and tmp.exists():
                tmp.unlink(missing_ok=True)

        inside_path = Path("/mnt/project") / task_path.relative_to(
            env.get_project_root()
        )
        res = subprocess.run(
            [
                "docker",
                "exec",
                self.container_name,
                "olive",
                "run-task",
                str(inside_path),
            ],
            capture_output=True,
            text=True,
        )
        if res.returncode:
            raise subprocess.CalledProcessError(
                res.returncode, res.args, res.stdout, res.stderr
            )

        if not wait or spec.return_id is None:
            return {
                "dispatched": True,
                "task_id": spec.id,
                "return_id": spec.return_id,
                "result_path": str(env.get_result_file(result_filename)),
            }

        result_path = env.get_result_file(result_filename)
        logger.info("Waiting for result via watchdog: %s", result_path)

        from olive.tasks.watcher import wait_file  # sync helper

        appeared = wait_file(result_path, timeout=None)
        if not appeared:
            raise TimeoutError(f"Task {spec.id}: result file never appeared")

        logger.info("✅ Result ready: %s", result_path)
        return json.loads(result_path.read_text())

    @docker_required
    async def dispatch_task_async(self, spec: TaskSpec) -> dict:
        """
        Legacy async wrapper — identical behaviour: run the blocking
        dispatch in a background thread so callers may `await` it.
        """
        return await asyncio.to_thread(self.dispatch_task, spec)

    @docker_required
    def dispatch_tool(self, toolname: str, args: list[str]) -> dict:
        if not self.is_running():
            raise RuntimeError("Sandbox is not running.")

        from shlex import quote

        cmdline = f"!!{toolname} {' '.join(quote(a) for a in args)}".strip()
        logger.info("Sending to sandbox daemon via tmux: %s", cmdline)

        target = f"olive-{env.get_session_id()}"
        res = subprocess.run(
            [
                "docker",
                "exec",
                self.container_name,
                "tmux",
                "send-keys",
                "-t",
                target,
                cmdline,
                "C-m",
            ],
            capture_output=True,
            text=True,
        )

        if res.stdout.strip():
            logger.debug("[sandbox stdout] %s", res.stdout.strip())
        if res.stderr.strip():
            logger.debug("[sandbox stderr] %s", res.stderr.strip())

        if res.returncode:
            raise RuntimeError(f"Failed to send command: {res.stderr.strip()}")

        return {
            "stdout": cmdline,
            "stderr": res.stderr.strip(),
            "returncode": res.returncode,
        }

    # ────────────────────────────────────────────── internals
    def _ensure_image(self) -> None:
        res = subprocess.run(
            ["docker", "images", "-q", "olive/sandbox:latest"],
            capture_output=True,
            text=True,
        )
        if not res.stdout.strip():
            logger.warning("Image not found – building…")
            self.build()

    def _hash_directory(self, path: Path) -> str:
        h = hashlib.sha1()
        for p in sorted(path.rglob("*")):
            if p.is_file():
                h.update(p.read_bytes())
        return h.hexdigest()

    def _disable_sandbox(self, prefs_path: Path) -> None:
        import yaml

        try:
            data = yaml.safe_load(prefs_path.read_text())
            data["sandbox"]["enabled"] = False
            prefs_path.write_text(yaml.safe_dump(data))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not disable sandbox in snapshot prefs: %s", exc)

    def is_running(self) -> bool:
        if self.container_name is None:
            return False

        # inside the sandbox snapshot we disabled the sandbox flag,
        # so short‑circuit early to avoid docker probes & noisy logs
        if not prefs.is_sandbox_enabled():
            return False
        try:
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name={self.container_name}"],
                capture_output=True,
                text=True,
            )
            return bool(result.stdout.strip())
        except FileNotFoundError:
            # only warn on the host, stay silent inside the sandbox
            logger.debug("[sandbox] Docker binary not available.")
            return False

    def _render_dockerfile(self, template: Path) -> str:
        """
        Returns the fully-materialised Dockerfile text.

        Placeholders handled:
          {{ extra_apt_packages }}
          {{ olive_source_path }}
          {{ olive_prefs_snapshot }}
        """

        # 0 · Setup banner ----------------------------------
        now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")
        banner = (
            "# ─────────────────────────────────────────\n"
            f"# 🚧 AUTOGENERATED DOCKERFILE – {now}\n"
            "# DO NOT EDIT — see Dockerfile.template\n"
            "# ─────────────────────────────────────────\n"
        )

        proj_root = env.get_project_root()
        olive_src = env.get_resource_path("olive").parent
        sbx_root = env.get_sandbox_root()
        snapshot_rel = (sbx_root / ".olive-snapshot").relative_to(proj_root)

        try:
            source_rel = olive_src.relative_to(proj_root)
        except ValueError:
            staging = sbx_root / "staging" / "olive"
            if staging.exists():
                shutil.rmtree(staging)
            shutil.copytree(olive_src, staging)
            source_rel = staging.relative_to(proj_root)

        # 1 · Optional extra apt packages ----------------------------------
        pkgs_cfg = prefs.get("sandbox", "environment", "extra_apt_packages", default=[])
        pkgs: list[str] = []
        if isinstance(pkgs_cfg, str):
            pkgs = [p for p in pkgs_cfg.split() if p.strip()]
        elif isinstance(pkgs_cfg, (list, tuple)):
            pkgs = [str(p).strip() for p in pkgs_cfg if str(p).strip()]
        extra_pkg_str = " ".join(f"{p}" for p in pkgs) if pkgs else ""

        # 3 · Instantiate the template ----------------------------------
        body = (
            template.read_text()
            .replace("{{ olive_user }}", "olive")
            .replace("{{ olive_source_path }}", str(source_rel))
            .replace("{{ olive_prefs_snapshot }}", str(snapshot_rel))
            .replace("{{ extra_apt_packages }}", str(extra_pkg_str))
        )

        return banner + "\n" + body.strip() + "\n"

    def _watched_paths(self) -> list[Path]:
        """Return every file that should trigger a rebuild when it changes."""
        proj_root = env.get_project_root()
        dot_olive = env.get_dot_olive()

        paths = [
            dot_olive / "settings" / "preferences.yml",
            env.get_resource_path("olive.sandbox", "Dockerfile.template"),
            env.get_resource_path("olive.sandbox", "entrypoint.sh"),
        ]

        # prompt files defined in prefs
        sys_prompt = prefs.get(
            "context", "system_prompt_path", default=".olive/settings/system_prompt.md"
        )
        builder_prompt = prefs.get(
            "builder_mode",
            "prompt_path",
            default=".olive/settings/builder_mode_prompt.txt",
        )
        paths += [
            (proj_root / sys_prompt).resolve(),
            (proj_root / builder_prompt).resolve(),
        ]
        return paths

    def _snapshot_hash(self) -> str:
        """Composite SHA-1 of project tree + watched config files."""
        import hashlib

        h = hashlib.sha1(
            self._hash_directory(env.get_dot_olive() / "settings/").encode()
        )
        for p in self._watched_paths():
            if p.exists():
                h.update(p.read_bytes())
        return h.hexdigest()

    def _auto_refresh(self) -> None:
        """Return True if any of our watched files changed and a re-build is required, otherwise False"""
        if not prefs.is_sandbox_enabled():
            return False

        try:
            marker = env.get_sandbox_root() / ".olive-snapshot" / ".snapshot_hash"
            if not marker.exists() or marker.read_text() != self._snapshot_hash():
                logger.warning("Sandbox config changed and requires a re-build.")
                return True
        except Exception as exc:
            logger.warning("Could not auto-refresh sandbox: %s", exc)

        return False


# ──────────────────────────────────────────────────────────────
# Singleton instance & shutdown hooks
# ──────────────────────────────────────────────────────────────
sandbox = SandboxManager()
atexit.register(sandbox.stop)
signal.signal(signal.SIGTERM, lambda *_: sandbox.stop())
signal.signal(signal.SIGINT, lambda *_: sandbox.stop())
