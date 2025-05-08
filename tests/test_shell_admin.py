import pytest
from unittest.mock import patch, MagicMock
import olive.shell.admin as shell_admin


def test_print_project_root(monkeypatch):
    monkeypatch.setattr(shell_admin.env, "get_project_root", lambda: "/proj")
    with patch("olive.shell.admin.print_secondary") as ps:
        shell_admin.print_project_root()
        ps.assert_called_once_with("olive project root: /proj")


def test_perform_graceful_exit(monkeypatch):
    with patch("olive.shell.admin.sys.exit") as sys_exit:
        shell_admin.perform_graceful_exit()
        sys_exit.assert_called_once_with(0)


def test_exit_command(monkeypatch):
    with patch("olive.shell.admin.perform_graceful_exit") as pe:
        shell_admin.perform_graceful_exit()
        pe.assert_called_once()


def test_help_command(monkeypatch):
    monkeypatch.setattr(
        shell_admin, "get_management_commands", lambda: {":foo": lambda: None}
    )
    with patch("olive.shell.admin.print_secondary") as ps:
        shell_admin.help_command()
        assert ps.call_count >= 2  # header + command line


def test_logs_command_with_pager(monkeypatch):
    monkeypatch.setattr(shell_admin, "get_current_log_file", lambda: "/tmp/log")
    monkeypatch.setattr(shell_admin, "which", lambda x: True)
    with patch("subprocess.run") as pr:
        shell_admin.logs_command()
        pr.assert_called()


def test_logs_command_no_pager(monkeypatch):
    monkeypatch.setattr(
        shell_admin,
        "get_current_log_file",
        lambda: MagicMock(read_text=lambda: "logdata"),
    )
    monkeypatch.setattr(shell_admin, "which", lambda x: False)
    with (
        patch("olive.shell.admin.print_info") as pi,
        patch("olive.shell.admin.console.print") as cp,
        patch("olive.shell.admin.print_warning") as pw,
    ):
        shell_admin.logs_command()
        assert pi.called and cp.called and pw.called


def test_reset_state_command(monkeypatch):
    monkeypatch.setattr("olive.logger.force_log_rotation", lambda: True)
    monkeypatch.setattr(shell_admin.context, "reset", lambda: None)
    with (
        patch("olive.shell.admin.print_warning") as pw,
        patch("olive.shell.admin.print_success") as ps,
        patch("olive.shell.admin.print_info") as pi,
    ):
        shell_admin.reset_state_command()
        assert pw.called and ps.called and pi.called


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_mock_ask_command(monkeypatch):
    monkeypatch.setattr(
        shell_admin.llm,
        "mock_ask",
        lambda prompt: (
            [],
            {
                "provider": "prov",
                "provider_base_url": "url",
                "model": "mod",
                "token_count": 3,
                "max_tokens": 8,
                "files": [],
            },
        ),
    )
    monkeypatch.setattr(shell_admin, "console", MagicMock(print=lambda *a, **k: None))
    monkeypatch.setattr(shell_admin, "print_highlight", lambda *a, **k: None)
    monkeypatch.setattr(shell_admin, "print_info", lambda *a, **k: None)
    monkeypatch.setattr(shell_admin, "print_success", lambda *a, **k: None)
    monkeypatch.setattr(shell_admin, "print_warning", lambda *a, **k: None)
    monkeypatch.setattr(shell_admin, "print_secondary", lambda *a, **k: None)
    monkeypatch.setattr(
        shell_admin,
        "tempfile",
        MagicMock(
            NamedTemporaryFile=MagicMock(
                return_value=MagicMock(
                    name="tmp", write=lambda x: None, close=lambda: None
                )
            )
        ),
    )
    monkeypatch.setattr(shell_admin.context, "hydrate", lambda: None)
    monkeypatch.setattr(shell_admin.context, "to_dict", lambda: {})
    await shell_admin.mock_ask_command()


def test_profile_command(monkeypatch):
    monkeypatch.setattr(
        shell_admin,
        "Table",
        MagicMock(
            return_value=MagicMock(
                add_column=lambda *a, **k: None, add_row=lambda *a, **k: None
            )
        ),
    )
    monkeypatch.setattr(shell_admin.context, "_discover_files", lambda: None)
    monkeypatch.setattr(shell_admin.context, "_build_context_payload", lambda: None)
    monkeypatch.setattr(shell_admin.context, "hydrate", lambda: None)
    monkeypatch.setattr(
        shell_admin,
        "LLMProvider",
        MagicMock(return_value=MagicMock(build_payload=lambda *a, **k: None)),
    )
    monkeypatch.setattr(shell_admin, "console", MagicMock(print=lambda *a, **k: None))
    shell_admin.profile_command()


def test_resume_command(monkeypatch):
    int_event = MagicMock(is_set=MagicMock(return_value=True), clear=MagicMock())
    monkeypatch.setattr(shell_admin, "_INTERRUPTED", int_event)
    with patch("builtins.print") as bp:
        shell_admin.resume_command()
        int_event.clear.assert_called_once()
        bp.assert_called()


def test_resume_command_not_paused(monkeypatch):
    int_event = MagicMock(is_set=MagicMock(return_value=False), clear=MagicMock())
    monkeypatch.setattr(shell_admin, "_INTERRUPTED", int_event)
    with patch("builtins.print") as bp:
        shell_admin.resume_command()
        bp.assert_called()
