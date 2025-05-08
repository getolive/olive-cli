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

def clear_active_spec_id(spec_id: str = None) -> str | None:
    active_spec_id = get_active_spec_id()
    if spec_id is not None and active_spec_id != spec_id:
        return None

    if not ACTIVE_SPEC_PATH or not ACTIVE_SPEC_PATH.exists():
        return None

    manifest_yml = yaml.safe_load(ACTIVE_SPEC_PATH.read_text())
    if manifest_yml.get("active_spec_id") != active_spec_id:
        return None

    # Remove the key
    manifest_yml.pop("active_spec_id", None)
    ACTIVE_SPEC_PATH.write_text(yaml.safe_dump(manifest_yml))
    return active_spec_id
