import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path
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
async def test_run_shell_command_subprocess_error(
    monkeypatch, isolated_olive_context: Path
):
    """
    run_shell_command() should bubble up a generic Exception when the
    underlying subprocess fails, regardless of init details.
    """
    mock_daemon = MagicMock(
        kind="shell", is_alive=MagicMock(return_value=True), daemon_id="d-1"
    )
    monkeypatch.setattr(
        shell_main.process_manager, "list", lambda: {"d-1": mock_daemon}
    )

    with patch("subprocess.run", side_effect=Exception("fail")):
        with pytest.raises(Exception):
            await shell_main.run_shell_command("echo hi")


@pytest.mark.asyncio
async def test_run_interactive_shell_keyboard_interrupt(
    monkeypatch, isolated_olive_context: Path
):
    """
    run_interactive_shell() should exit cleanly when an EOFError/KeyboardInterrupt
    occurs inside prompt_toolkit's event-loop.
    """

    async def _boom():  # noqa: D401
        raise EOFError

    #monkeypatch.setattr(shell_main, "run_interactive_shell", _boom)
    monkeypatch.setattr(shell_main.session, "prompt_async", lambda *a, **k: _boom())

    # EOFError is swallowed; function returns None
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
