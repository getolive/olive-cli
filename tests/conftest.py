import pytest

@pytest.fixture(scope="session", autouse=True)
def set_olive_project_root_early(tmp_path_factory):
    # Create a dedicated session temp directory and set Olive project root
    test_root = tmp_path_factory.mktemp("olive_session_root")
    from olive.env import set_project_root
    set_project_root(test_root)
    return test_root


@pytest.fixture(autouse=True)
def patch_specs_dir(monkeypatch, tmp_path):
    """Globally patch get_specs_dir for all tests to use a temp directory."""
    from olive.canonicals.spec import storage

    monkeypatch.setattr(storage, "get_specs_dir", lambda: tmp_path)


@pytest.fixture
def reset_task_manager():
    from olive.tasks import task_manager

    old_tasks = dict(getattr(task_manager, "_tasks", {}))
    if hasattr(task_manager, "_tasks"):
        task_manager._tasks.clear()
    yield
    if hasattr(task_manager, "_tasks"):
        task_manager._tasks.clear()
        task_manager._tasks.update(old_tasks)


@pytest.fixture
def reset_olive_context():
    from olive.context import OliveContext

    ctx = OliveContext()
    _ = ctx.to_dict()
    ctx.reset()  # Clear to default state
    try:
        yield
    finally:
        ctx.reset()  # Clear again after test


def _olive_is_initted():
    from olive.env import get_dot_olive

    dot_olive = get_dot_olive()
    return dot_olive.exists() and dot_olive.is_dir()


@pytest.fixture(autouse=True, scope="session")
def ensure_olive_initted():
    """
    Ensure Olive is initialized (.olive exists) before running tests.
    If already initialized, do nothing. If missing, initialize using Olive's API.
    """
    if not _olive_is_initted():
        from olive.init import initialize_olive

        initialize_olive()

@pytest.fixture
def isolated_olive_context(monkeypatch, tmp_path):
    from pathlib import Path
    import olive.env
    import olive.context

    # Save the original project root
    orig_project_root = getattr(olive.env, "_PROJECT_ROOT", None)
    olive.env._PROJECT_ROOT = tmp_path.resolve()
    monkeypatch.setattr(olive.env, "get_dot_olive", lambda: tmp_path / ".olive")

    # Re-instantiate the context singleton to use the new project root
    olive.context.context = olive.context.OliveContext()

    yield tmp_path

    # Restore the original project root and context singleton after the test
    if orig_project_root is not None:
        olive.env._PROJECT_ROOT = orig_project_root
    else:
        olive.env._PROJECT_ROOT = Path.cwd().resolve()
    olive.context.context = olive.context.OliveContext()


