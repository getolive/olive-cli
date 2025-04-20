# olive/spec/state.py
import yaml

from olive.canonicals.spec.storage import get_specs_dir

ACTIVE_SPEC_PATH = get_specs_dir() / "manifest.yml"


def get_active_spec_id() -> str | None:
    if ACTIVE_SPEC_PATH.exists():
        return yaml.safe_load(ACTIVE_SPEC_PATH.read_text()).get("active_spec_id")
    return None


def set_active_spec_id(spec_id: str):
    ACTIVE_SPEC_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_SPEC_PATH.write_text(yaml.safe_dump({"active_spec_id": spec_id}))
