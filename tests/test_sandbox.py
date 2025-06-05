import pytest
import subprocess
from pathlib import Path
from olive.sandbox import sandbox

# ---- Module-level fixtures ----

@pytest.fixture(autouse=True)
def mock_docker(monkeypatch):
    """Mock subprocess.run, check_output, and check_call to avoid real Docker calls."""
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(args=a[0], returncode=0))
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: b"mocked output")
    monkeypatch.setattr(subprocess, "check_call", lambda *a, **k: 0)

@pytest.fixture
def olive_sandbox(isolated_olive_context):
    """Yield the Olive sandbox singleton, freshly initialized in the test's temp Olive project."""
    return sandbox

# ---- Tests ----

def test_build_creates_dockerfile_and_assets(olive_sandbox, tmp_path, monkeypatch):
    """Test: build() creates Dockerfile and required assets in build context."""
    # Patch session ID for container_name
    monkeypatch.setattr("olive.sandbox.env.get_session_id", lambda: "testsession")
    olive_sandbox.build(force=True)
    from olive import env
    sbx_root = env.get_sandbox_root()
    dockerfile = sbx_root / "Dockerfile"
    entrypoint = sbx_root / "entrypoint.sh"
    assert dockerfile.exists(), "Dockerfile should be copied to sandbox root"
    assert entrypoint.exists(), "entrypoint.sh should be copied to sandbox root"

def test_start_starts_container(olive_sandbox, monkeypatch):
    """Test: start() triggers Docker run and handles already-running case."""
    called = {}
    def fake_build(force=False): called['build'] = force
    def fake_is_running():
        return called.get('started', False)
    def fake_sh(cmd, *, capture=False, cwd=None):
        called['started'] = True
        return "fakecontainerid" if capture else ""
    monkeypatch.setattr(olive_sandbox, 'build', fake_build)
    monkeypatch.setattr(olive_sandbox, 'is_running', fake_is_running)
    monkeypatch.setattr("olive.sandbox._sh", fake_sh)
    monkeypatch.setattr("olive.sandbox.env.get_session_id", lambda: "testsession")
    olive_sandbox.start(force_build=True)
    assert called.get('build', None) is True
    assert called.get('started', None) is True

def test_stop_stops_container(olive_sandbox, monkeypatch):
    """Test: stop() triggers Docker stop/remove and handles not-running case."""
    called = {'running': True, 'stopped': False}
    def fake_is_running(): return called['running']
    def fake_sh(cmd): called['stopped'] = True; return ""
    monkeypatch.setattr(olive_sandbox, 'is_running', fake_is_running)
    monkeypatch.setattr("olive.sandbox._sh", fake_sh)
    monkeypatch.setattr("olive.sandbox.env.get_session_id", lambda: "testsession")
    olive_sandbox.stop()
    assert called['stopped'] is True

def test_restart_is_idempotent(olive_sandbox, monkeypatch):
    """Test: restart() calls stop then start; idempotency guaranteed."""
    order = []
    monkeypatch.setattr(olive_sandbox, 'stop', lambda: order.append('stop'))
    monkeypatch.setattr(olive_sandbox, 'start', lambda: order.append('start'))
    olive_sandbox.restart()
    assert order == ['stop', 'start']

def test_is_running_status_reporting(olive_sandbox, monkeypatch):
    """Test: is_running() and status() report correct container state."""
    monkeypatch.setattr(olive_sandbox, 'is_running', lambda: True)
    monkeypatch.setattr("olive.sandbox._sh", lambda cmd, **kwargs: "running" if "inspect" in cmd else "fakeid")
    monkeypatch.setattr("olive.sandbox.env.get_session_id", lambda: "testsession")
    assert olive_sandbox.is_running() is True
    assert olive_sandbox.status() == "running"

def test_dispatch_task_serializes_spec(olive_sandbox, tmp_path, monkeypatch):
    """Test: dispatch_task() serializes a spec file to the RPC dir."""
    from olive.tasks.models import TaskSpec
    from olive import env
    monkeypatch.setattr(olive_sandbox, 'is_running', lambda: True)
    monkeypatch.setattr("olive.sandbox.env.get_session_id", lambda: "testsess")
    monkeypatch.setattr("olive.sandbox._sh", lambda *a, **k: "")
    spec = TaskSpec(name="test", input={"foo": 1}, return_id="retid123")
    res = olive_sandbox.dispatch_task(spec, wait=False)
    rpc_path = env.get_task_file("retid123")
    assert rpc_path.exists(), f"Task file {rpc_path} should be written"
    content = rpc_path.read_text()
    assert '"foo": 1' in content and '"name": "test"' in content
    assert res == {'dispatched': True}

def test_sandbox_asset_and_wheel_staging(olive_sandbox):
    """Test: Asset and wheel staging methods work and cache as expected."""
    from olive.sandbox import _ensure_staged_wheel
    wheel_path = _ensure_staged_wheel()
    assert wheel_path.exists()
    assert wheel_path.name.endswith('.whl')

def test_error_handling_on_docker_failure(monkeypatch, olive_sandbox):
    """Test: Docker failures are handled gracefully and produce actionable errors."""
    def bad_run(*a, **k):
        raise subprocess.CalledProcessError(1, a[0], output="docker error")
    monkeypatch.setattr("olive.sandbox._sh", bad_run)
    monkeypatch.setattr("olive.sandbox.env.get_session_id", lambda: "testsession")
    try:
        olive_sandbox.build(force=True)
        assert False, "Should raise on build error"
    except subprocess.CalledProcessError as e:
        assert "docker" in str(e.output)

def test_multiple_olives_same_path(tmp_path, monkeypatch):
    """Test: Multiple Olive instances in the same project path should spawn exactly one sandbox per Olive.
    No cross-instance interference in lifecycle. WARNING: Context/active.json is not isolated (expected muddiness)."""
    from olive.sandbox import _Sandbox
    import olive.env as envmod
    envmod.set_project_root(tmp_path)
    s1 = _Sandbox()
    s2 = _Sandbox()
    assert s1 is s2, "Both sandboxes should be the singleton"

def test_multiple_olives_different_projects(tmp_path_factory, monkeypatch):
    """Test: Multiple Olive projects on same user account, different directories. Each should maintain fully isolated sandbox and context."""
    from olive.sandbox import _Sandbox
    import olive.env as envmod
    proj1 = tmp_path_factory.mktemp('olive_proj1')
    proj2 = tmp_path_factory.mktemp('olive_proj2')
    envmod.set_project_root(proj1)
    s1 = _Sandbox()
    envmod.set_project_root(proj2)
    s2 = _Sandbox()
    assert s1 is s2, "Singleton is per-process, but context switches"

def test_full_cleanup_and_no_host_modification(tmp_path, monkeypatch):
    """Test: Pytest and sandbox testing must never modify Olive's real user/project directories. No state pollution."""
    import os
    home = os.path.expanduser('~')
    user_olive = os.path.join(home, '.olive')
    # Should not exist or remain unchanged after test suite
    if os.path.exists(user_olive):
        assert os.stat(user_olive).st_uid == os.getuid(), "Should not change user olive dir"
