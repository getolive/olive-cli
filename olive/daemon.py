# cli/olive/daemon.py
import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from olive.env import get_project_root
from olive.logger import get_logger

logger = get_logger("daemon")

_proj = get_project_root() or Path.cwd()
OLIVE_RUN_DIR = (_proj / ".olive" / "run").resolve()
OLIVE_LOGS_DIR = OLIVE_RUN_DIR.parent / "logs"
DAEMON_LOG = OLIVE_LOGS_DIR / (os.getenv("OLIVE_SESSION_ID", "default") + "/daemon.log")


class ProcessInfo:
    def __init__(self, *, daemon_id: str, pid: int, kind: str):
        self.daemon_id = daemon_id
        self.pid = pid
        self.kind = kind
        self.path = OLIVE_RUN_DIR / f"{daemon_id}.json"

    def save(self):
        OLIVE_RUN_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "daemon_id": self.daemon_id,
            "pid": self.pid,
            "kind": self.kind,
        }
        with open(self.path, "w") as f:
            json.dump(data, f)
        logger.debug(f"Saved process info: {data} -> {self.path}")

    @classmethod
    def load(cls, daemon_id: str) -> Optional["ProcessInfo"]:
        path = OLIVE_RUN_DIR / f"{daemon_id}.json"
        if not path.exists():
            logger.warning(f"No process metadata found for daemon ID: {daemon_id}")
            return None
        try:
            with open(path, "r") as f:
                data = json.load(f)
            logger.debug(f"Loaded process info for {daemon_id}: {data}")
            return cls(
                daemon_id=data["daemon_id"],
                pid=data["pid"],
                kind=data.get("kind"),
            )
        except Exception as e:
            logger.error(f"Failed to load process metadata for {daemon_id}: {e}")
            return None

    @classmethod
    def all(cls) -> Dict[str, "ProcessInfo"]:
        if not OLIVE_RUN_DIR.exists():
            return {}
        entries = {}
        for f in OLIVE_RUN_DIR.glob("*.json"):
            try:
                with open(f, "r") as meta:
                    data = json.load(meta)
                    proc = cls(
                        daemon_id=data["daemon_id"],
                        pid=data["pid"],
                        kind=data.get("kind", "unknown"),
                    )
                    entries[proc.daemon_id] = proc
            except Exception as e:
                logger.warning(f"Failed to load process file {f}: {e}")
        logger.debug(f"Discovered {len(entries)} running processes")
        return entries

    def is_alive(self) -> bool:
        try:
            subprocess.run(
                ["tmux", "has-session", "-t", self.daemon_id],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            logger.debug(f"tmux session for {self.daemon_id} is alive")
            return True
        except subprocess.CalledProcessError:
            logger.debug(f"tmux session for {self.daemon_id} is NOT alive")
            return False

    def delete(self):
        if self.path.exists():
            self.path.unlink()
            logger.debug(f"Deleted process metadata for daemon ID {self.daemon_id}")

    def kill(self):
        try:
            subprocess.run(["tmux", "kill-session", "-t", self.daemon_id], check=True)
            logger.info(f"TODO: not implemented properly yet ::: Killed tmux session for daemon ID {self.daemon_id}")
            self.delete()
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to kill tmux session {self.daemon_id}: {e}")
            return False


class ProcessManager:
    def list(self) -> Dict[str, ProcessInfo]:
        return ProcessInfo.all()

    def get(self, daemon_id: str) -> Optional[ProcessInfo]:
        return ProcessInfo.load(daemon_id)

    def kill(self, daemon_id: str) -> bool:
        proc = self.get(daemon_id)
        return proc.kill() if proc else False

    def save(self, proc: ProcessInfo):
        proc.save()

    def spawn(
        self, daemon_id: str, cmd: List[str], kind: str = "shell"
    ) -> Optional[ProcessInfo]:
        session_name = daemon_id.replace("_", "-")
        command_str = shlex.join(cmd)
        try:
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", session_name, command_str],
                check=True,
            )
            logger.info(
                f"Started tmux session '{session_name}' for daemon ID {daemon_id}"
            )

            # We can't get the child PID directly from tmux, so we use a dummy
            dummy_pid = -1
            proc = ProcessInfo(daemon_id=daemon_id, pid=dummy_pid, kind=kind)
            self.save(proc)
            return proc
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to start tmux session for daemon ID {daemon_id}: {e}")
            return None


process_manager = ProcessManager()
