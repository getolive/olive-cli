import pytest

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
    old_state = ctx.to_dict()
    ctx.reset()  # Clear to default state
    try:
        yield
    finally:
        ctx.reset()  # Clear again after test
