# cli/olive/canonicals/spec/models.py
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Literal, Optional

import yaml
from pydantic import BaseModel

from olive.canonicals.utils import SafeYAMLSaveMixin


class FeatureSpec(BaseModel, SafeYAMLSaveMixin):
    """A FeatureSpec is a summarized unit of work that we want to get done.
    It can be big like an epic or small like a task (or anything in between)."""

    id: str
    title: str
    description: str
    files_affected: List[str] = []
    acceptance_criteria: List[str] = []
    status: Literal["open", "in-progress", "complete", "cancelled"] = "open"
    created_at: datetime
    branch: Optional[str] = None

    # ✅ Fix missing fields
    subtasks: List[dict] = []
    comments: List[str] = []

    def __str__(self):
        return f"[{self.status}] {self.title} ({self.id})"

    @staticmethod
    def get_specs_dir() -> Path:
        return Path(".olive/specs")

    def filename(self) -> str:
        return f"{self.get_specs_dir()}/{self.id}.yml"

    @classmethod
    def load(cls, spec_id: str) -> "FeatureSpec":
        path = Path(f".olive/specs/{spec_id}.yml")
        if not path.exists():
            raise FileNotFoundError(f"Spec not found: {spec_id}")
        return cls(**yaml.safe_load(path.read_text()))

    def save(self):
        Path(".olive/specs").mkdir(parents=True, exist_ok=True)
        self.safe_save_yaml(Path(self.filename()), self.model_dump(exclude_none=True))

    def mark_complete(self, commit: bool = True, message: Optional[str] = None):
        self.status = "complete"
        self.save()
        if commit:
            self._commit(message or f"chore: mark spec {self.id} complete")

    def mark_cancelled(self, commit: bool = True, message: Optional[str] = None):
        self.status = "cancelled"
        self.save()
        if commit:
            self._commit(message or f"chore: cancel spec {self.id}")

    def _commit(self, message: str):
        # we do -f now because .olive/specs will be commitable.
        subprocess.run(["git", "add", "-f", self.filename()], check=True)
        subprocess.run(["git", "commit", "-m", message], check=True)

        # 🧠 Check for other uncommitted changes
        result = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True
        )
        if result.stdout.strip():
            print(
                "[yellow]⚠️ You have other uncommitted changes in this branch.[/yellow]"
            )
            print(
                "[dim]Run `git add`, `git commit`, and `git merge` when you're ready to fully resolve this spec.[/dim]"
            )

    @classmethod
    def create(cls, title: str, description: str) -> "FeatureSpec":
        now = datetime.now()
        id_slug = now.strftime("%Y%m%d_%H%M%S")
        branch = f"feat/{id_slug.replace('_', '-')}"

        spec = cls(
            id=id_slug,
            title=title,
            description=description,
            files_affected=[],
            acceptance_criteria=[
                "Code is committed",
                "Tests pass",
                "Feature is callable via shell",
            ],
            created_at=now,
            branch=branch,
        )
        spec.save()
        subprocess.run(["git", "checkout", "-b", branch], check=True)
        return spec
