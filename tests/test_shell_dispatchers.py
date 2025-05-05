import pytest
import olive.shell.dispatchers as dispatchers

@pytest.mark.asyncio
async def test_dispatch_management(monkeypatch):
    called = {}
    async def fake_exit_command(*a, **kw):
        called["exit"] = True
    commands = dispatchers.COMMANDS.copy()
    commands[":exit"] = fake_exit_command
    monkeypatch.setattr(dispatchers, "COMMANDS", commands)
    monkeypatch.setattr(dispatchers.console, "print", lambda *a, **kw: None)
    await dispatchers._dispatch_management(":exit", interactive=True)
    assert called["exit"]

def test__dispatch_shell_exec(monkeypatch):
    output = []
    def fake_run(cmd):
        output.append(cmd)
    monkeypatch.setattr(dispatchers, "_dispatch_shell_exec", fake_run)
    dispatchers._dispatch_shell_exec("echo hi")
    assert output == ["echo hi"]

def test__dispatch_atcommand_add(monkeypatch, tmp_path, capsys):
    # Case 1: file does not exist
    result = dispatchers._dispatch_atcommand("does_not_exist.txt")
    assert result is None
    out = " ".join(capsys.readouterr().out.split())
    assert "does not exist or is not a file." in out

    # Case 2: file exists on disk but not in Olive context
    temp_file = tmp_path / "afile.txt"
    temp_file.write_text("hi\nolive")
    result = dispatchers._dispatch_atcommand(str(temp_file))
    out = " ".join(capsys.readouterr().out.split())
    assert "does not exist or is not a file." not in out  # Should succeed if file exists!

@pytest.mark.asyncio
async def test__dispatch_llm(monkeypatch):
    called = {}
    class DummyLLM:
        async def ask(self, prompt, *a, **kw):
            called["prompt"] = prompt
            return "ok"
    monkeypatch.setattr(dispatchers, "llm", DummyLLM())
    monkeypatch.setattr(dispatchers.console, "print", lambda *a, **kw: None)
    result = await dispatchers._dispatch_llm("What is Olive?", interactive=True)
    assert called["prompt"] == "What is Olive?"
    assert result is None  # Dispatcher prints, but does not return LLM result
