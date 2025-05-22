from unittest.mock import MagicMock
import olive.init as init_main
from olive import env
from pathlib import Path
import pytest

import subprocess


def test_safe_add_extra_context_file_success(tmp_path):
    import olive
    from olive.context.utils import (
        safe_add_extra_context_file,
        safe_remove_extra_context_file,
    )

    old_root = olive.env.get_project_root()
    olive.env.set_project_root(tmp_path)
    test_file = tmp_path / "hello.txt"
    test_file.write_text("abc\ndef")
    safe_remove_extra_context_file(str(test_file))
    assert safe_add_extra_context_file(str(test_file))
    safe_remove_extra_context_file(str(test_file))
    olive.env.set_project_root(old_root)


def test_safe_add_extra_context_file_excluded(tmp_path, monkeypatch):
    from olive.context.utils import (
        safe_add_extra_context_file,
        safe_remove_extra_context_file,
    )
    from olive.context import context

    context.reset()
    context.hydrate()
    test_file = tmp_path / "exclude.txt"
    test_file.write_text("abc")
    monkeypatch.setattr(context, "is_file_excluded", lambda p: True)
    assert not safe_add_extra_context_file(str(test_file), force=False)
    assert safe_add_extra_context_file(str(test_file), force=True)
    safe_remove_extra_context_file(str(test_file))


def test_safe_remove_extra_context_file_success(tmp_path):
    from olive.context.utils import (
        safe_add_extra_context_file,
        safe_remove_extra_context_file,
    )

    test_file = tmp_path / "remove.txt"
    test_file.write_text("123")
    safe_add_extra_context_file(str(test_file))
    assert safe_remove_extra_context_file(str(test_file))
    assert safe_remove_extra_context_file(str(test_file))


def test_safe_remove_extra_context_file_notfound(tmp_path):
    from olive.context.utils import safe_remove_extra_context_file

    test_file = tmp_path / "notfound.txt"
    test_file.write_text("doesn't matter")
    assert safe_remove_extra_context_file(str(test_file))


def test_get_git_diff_stats(monkeypatch):
    from olive.context import utils

    monkeypatch.setattr(
        "subprocess.run", lambda *a, **k: MagicMock(stdout="1\t2\tfile.py\n")
    )
    stats = utils.get_git_diff_stats()
    assert "file.py" in stats


def test_initialize_creates_project_scaffolding(tmp_path: Path):
    """
    `initialize_olive(path)` must always create:

        <path>/.olive/context/active.json
        <path>/.olive/settings/
    """

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    env.set_project_root(tmp_path)

    init_main.initialize_olive(tmp_path)

    settings_dir = tmp_path / ".olive" / "settings"

    # settings dir should contain at least the two mandatory YAML files
    assert {f.name for f in settings_dir.iterdir()} >= {
        "preferences.yml",
        "credentials.yml",
    }


@pytest.fixture
def isolated_home(monkeypatch, tmp_path: Path):
    """
    Redirect USER_OLIVE and env.get_user_root() to a temp dir so the test
    never touches ~/.olive on the developer or CI runner.
    """

    fake_home_olive = tmp_path / "_home_olive"
    monkeypatch.setattr(init_main, "USER_OLIVE", fake_home_olive, raising=False)
    monkeypatch.setattr(env, "get_user_root", lambda: fake_home_olive)
    return fake_home_olive


def test_user_and_project_settings_propagation(tmp_path: Path, monkeypatch):
    """
    1. Provide a throw-away dotfile_defaults set.
    2. Verify those files copy into USER_OLIVE.
    3. Verify they propagate into <project>/.olive/settings exactly once.
    """

    # ------------------------------------------------------------------ #
    # 0 · mock machine-level paths
    # ------------------------------------------------------------------ #
    fake_home = tmp_path / "_home_olive"
    monkeypatch.setattr(init_main, "USER_OLIVE", fake_home, raising=False)
    monkeypatch.setattr(env, "get_user_root", lambda: fake_home)

    # Provide a minimal dotfile_defaults dir for this test run
    fake_defaults = tmp_path / "_defaults"
    fake_defaults.mkdir()
    (fake_defaults / "preferences.yml").write_text("sandbox:\n  enabled: true\n")
    (fake_defaults / "credentials.yml").write_text("provider: dummy\n")
    monkeypatch.setattr(init_main, "DOTFILE_DEFAULTS", fake_defaults, raising=False)

    # ------------------------------------------------------------------ #
    # 1 · machine-level copy runs once
    # ------------------------------------------------------------------ #
    copied_user, _ = init_main._ensure_user_olive()
    assert {"preferences.yml", "credentials.yml"} <= set(copied_user)

    # ------------------------------------------------------------------ #
    # 2 · project-level propagation
    # ------------------------------------------------------------------ #
    project_root = tmp_path / "proj"
    project_root.mkdir()
    subprocess.run(["git", "init", "-q", str(project_root)], check=True)
    env.set_project_root(project_root)

    init_main.initialize_olive(project_root)

    settings_dir = project_root / ".olive" / "settings"
    assert {"preferences.yml", "credentials.yml"} <= {
        p.name for p in settings_dir.iterdir() if p.is_file()
    }

    # ------------------------------------------------------------------ #
    # 3 · idempotency – no second copy
    # ------------------------------------------------------------------ #
    copied_again, _ = init_main._sync_project_settings()
    assert not copied_again, "second initialise copied files again unexpectedly"
