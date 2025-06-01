# olive-cli/tests/conftest.py
import pytest
import subprocess
from pathlib import Path
from olive import init
import os


# ───────────────────────────────────────────────────────────────
#  Session-level project root (one per pytest run)
# ───────────────────────────────────────────────────────────────
@pytest.fixture(scope="session", autouse=True)
def set_olive_project_root_early(tmp_path_factory):
    """
    Create a dedicated temp directory, initialise an empty Git repo and
    tell Olive this is the project root for *all* tests.
    """
    test_root = tmp_path_factory.mktemp("olive_session_root")

    # real-world invariant: Olive insists on being inside a Git work-tree
    subprocess.run(["git", "init", "-q", str(test_root)], check=True)
    subprocess.run(
        ["git", "-C", str(test_root), "config", "user.email", "olive-test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(test_root), "config", "user.name", "Olive Test"], check=True
    )
    subprocess.run(
        ["git", "-C", str(test_root), "commit", "--allow-empty", "-m", "test-root"],
        check=True,
    )

    from olive.init import initialize_olive
    from olive.env import set_project_root

    # monkeypatch.setattr(env, "get_user_root", lambda: user_root)
    # monkeypatch.setattr(init, "USER_OLIVE", user_root)
    set_project_root(test_root)
    initialize_olive(test_root)
    print("DEBUG: HOME =", os.environ.get("HOME"))
    print("DEBUG: USER_OLIVE =", init.USER_OLIVE)
    print("DEBUG: USER_OLIVE exists =", init.USER_OLIVE.exists())
    print(
        "DEBUG: USER_OLIVE/preferences.yml exists =",
        (init.USER_OLIVE / "preferences.yml").exists(),
    )
    return test_root


# ───────────────────────────────────────────────────────────────
#  Specs dir redirect (per-test)
# ───────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def patch_specs_dir(monkeypatch, tmp_path):
    """Force specs storage into a temp dir so tests never pollute ~/.olive."""
    from olive.canonicals.spec import storage

    monkeypatch.setattr(storage, "get_specs_dir", lambda: tmp_path)


# ───────────────────────────────────────────────────────────────
#  Task manager + context reset helpers (unchanged)
# ───────────────────────────────────────────────────────────────
@pytest.fixture
def reset_task_manager():
    from olive.tasks import task_manager

    old_tasks = dict(getattr(task_manager, "_tasks", {}))
    task_manager._tasks.clear()
    yield
    task_manager._tasks.clear()
    task_manager._tasks.update(old_tasks)


@pytest.fixture
def reset_olive_context():
    from olive.context import context

    _ = context.to_dict()  # materialise
    context.reset()
    try:
        yield
    finally:
        context.reset()


# ───────────────────────────────────────────────────────────────
#  Initialise Olive once per session
# ───────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True, scope="session")
def ensure_olive_initted(set_olive_project_root_early):
    """
    Run Olive bootstrap against the pre-created session root if not already
    done.  Uses the *path* arg so Git check is relaxed (though we did init).
    """
    from olive.init import initialize_olive

    initialize_olive(set_olive_project_root_early)


# ───────────────────────────────────────────────────────────────
#  Per-test sandbox: isolated project root + context
# ───────────────────────────────────────────────────────────────
@pytest.fixture
def isolated_olive_context(monkeypatch, tmp_path):
    """
    Each test gets its own clean .olive workspace + context singleton.
    """
    import olive.env
    import olive.context

    # 1 · make the temp dir a Git work-tree
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)

    # 2 - point olive at it
    olive.env._PROJECT_ROOT = tmp_path.resolve()
    monkeypatch.setattr(olive.env, "get_dot_olive", lambda: tmp_path / ".olive")

    # fresh context singleton wired to that root
    olive.context.context = olive.context.OliveContext()

    yield tmp_path

    # tear-down: restore global defaults
    olive.env._PROJECT_ROOT = Path.cwd().resolve()
    olive.context.context = olive.context.OliveContext()
