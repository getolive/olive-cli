from olive.preferences import Preferences


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
