import pytest
from olive.preferences import Preferences
from olive.sandbox import sandbox
from olive import env


def test_base_apt_packages_loaded(monkeypatch, tmp_path, set_olive_project_root_early):
    # Write a temp preferences.yml with exactly the expected value
    prefs_file = tmp_path / ".olive" / "preferences.yml"
    prefs_file.parent.mkdir(parents=True, exist_ok=True)
    prefs_file.write_text(
        """
sandbox:
  environment:
    base_apt_packages:
      - git
      - curl
      - build-essential
"""
    )
    # Monkeypatch Preferences to load from this file
    monkeypatch.setattr(
        Preferences, "get_preferences_path", lambda self: (prefs_file, True)
    )
    prefs = Preferences()
    pkgs = prefs.get("sandbox", "environment", "base_apt_packages")
    assert pkgs == ["git", "curl", "build-essential"]


@pytest.mark.asyncio
async def test_extra_apt_packages_injection(monkeypatch, set_olive_project_root_early):
    """
    `_render_dockerfile()` must inject extra apt packages and remove the
    placeholder when preferences specify a list.

    NOTE: Uses set_olive_project_root_early as the only project root source of truth,
    so paths are aligned with Olive internals.
    """

    # real template shipped with Olive
    template = env.get_resource_path("olive.sandbox", "Dockerfile.template")

    # Monkey-patch Preferences.get to inject extra apt packages
    _orig_get = Preferences.get

    def _patched_get(self, *keys, default=None):
        if keys[-1] in {"base_apt_packages", "extra_apt_packages"}:
            return ["vim", "htop"]
        return _orig_get(self, *keys, default=default)

    monkeypatch.setattr(Preferences, "get", _patched_get, raising=False)

    # Render Dockerfile and assert injections (rest of your test logic here)
    rendered = sandbox._render_dockerfile(template)

    # --- assertions go here, for example: ---
    assert "vim" in rendered
    assert "htop" in rendered
    assert "## OLIVE-EXTRA-APT-PACKAGES" not in rendered


"""
@pytest.mark.asyncio
async def test_extra_apt_packages_injection(monkeypatch, isolated_olive_context: Path, set_olive_project_root_early):
    #_render_dockerfile()` must inject extra apt packages and remove the placeholder when preferences specify a list.
    # ------------------------------------------------------------------ #
    # 0 · ensure sandbox singleton points at the isolated context
    # ------------------------------------------------------------------ #

    # real template shipped with Olive
    template = env.get_resource_path("olive.sandbox", "Dockerfile.template")

    # ------------------------------------------------------------------ #
    # 1 · monkey-patch Preferences.get  (delegate for all other keys)
    # ------------------------------------------------------------------ #
    _orig_get = Preferences.get

    def _patched_get(self, *keys, default=None):
        if keys[-1] in {"base_apt_packages", "extra_apt_packages"}:
            return ["vim", "htop"]
        return _orig_get(self, *keys, default=default)

    monkeypatch.setattr(Preferences, "get", _patched_get, raising=False)

    # ------------------------------------------------------------------ #
    # 2 · render Dockerfile and assert injections
    # ------------------------------------------------------------------ #
    rendered = sandbox._render_dockerfile(template)

    assert "vim" in rendered and "htop" in rendered, "packages not injected"
    assert "{{ extra_apt_packages" not in rendered.lower(), "placeholder not removed"
"""
