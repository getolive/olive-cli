import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import olive.shell.__init__ as shell_main
from olive import init as init_main

@pytest.mark.asyncio
async def test_run_shell_command_forwards_to_single_daemon(monkeypatch):
    from unittest.mock import MagicMock
    import olive.shell.__init__ as shell_main

    mock_daemon = MagicMock(
        kind="shell", is_alive=MagicMock(return_value=True), daemon_id="daemon-1"
    )
    monkeypatch.setattr(shell_main.process_manager, "list", lambda: {"d1": mock_daemon})
    with patch("subprocess.run") as mock_run:
        await shell_main.run_shell_command("echo hi")
        mock_run.assert_called_once()


@pytest.mark.asyncio
async def test_run_shell_command_multiple_daemons(monkeypatch):
    from unittest.mock import MagicMock, AsyncMock
    import olive.shell.__init__ as shell_main

    d1 = MagicMock(kind="shell", is_alive=MagicMock(return_value=True))
    d2 = MagicMock(kind="shell", is_alive=MagicMock(return_value=True))
    monkeypatch.setattr(
        shell_main.process_manager, "list", lambda: {"d1": d1, "d2": d2}
    )
    with patch(
        "olive.shell.__init__.dispatch", new_callable=AsyncMock
    ) as mock_dispatch:
        await shell_main.run_shell_command("echo hi")
        mock_dispatch.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_shell_command_subprocess_error(monkeypatch):
    from unittest.mock import MagicMock
    import olive.shell.__init__ as shell_main

    mock_daemon = MagicMock(
        kind="shell", is_alive=MagicMock(return_value=True), daemon_id="daemon-1"
    )
    monkeypatch.setattr(shell_main.process_manager, "list", lambda: {"d1": mock_daemon})
    with patch("subprocess.run", side_effect=Exception("fail")):
        with pytest.raises(Exception):
            await shell_main.run_shell_command("echo hi")

    # Should exit on KeyboardInterrupt
    await shell_main.run_interactive_shell()


@pytest.mark.asyncio
async def test_run_interactive_shell_eoferror(monkeypatch):
    monkeypatch.setattr(init_main, "initialize_shell_session", lambda: None)
    monkeypatch.setattr(shell_main, "register_commands", lambda cmds: None)
    session_mock = MagicMock()
    session_mock.prompt_async = AsyncMock(side_effect=EOFError)
    monkeypatch.setattr(shell_main, "session", session_mock)
    monkeypatch.setattr(shell_main, "olive_prompt", "> ")
    monkeypatch.setattr(shell_main, "dispatch", AsyncMock())
    # Should exit on EOFError
    await shell_main.run_interactive_shell()
