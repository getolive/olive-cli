import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
import olive.prompt_ui as pui

def test_command_registry():
    fn = lambda: 'ok'
    pui._command_lookup.clear()
    pui.register_commands({':foo': fn})
    assert pui.get_management_commands()[':foo'] is fn

def test_olive_management_command_decorator():
    pui._command_lookup.clear()
    @pui.olive_management_command(':bar')
    def handler(): return 42
    assert ':bar' in pui._command_lookup

def test_safe_command_sync(monkeypatch):
    called = {}
    def fn(): called['ok'] = True; raise Exception('fail')
    with patch('olive.prompt_ui.print_error') as pe, patch('olive.prompt_ui.logger') as lg:
        wrapped = pui.safe_command(fn)
        wrapped()
        assert called['ok'] and pe.called and lg.exception.called

@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_safe_command_async(monkeypatch):
    import olive.prompt_ui as prompt_ui
    called = {}
    async def fn():
        called['ok'] = True
        raise Exception('fail')
    safe = prompt_ui.safe_command(fn)
    try:
        await safe()
    except Exception:
        pass
    assert called['ok']

def test_olive_completer_management(monkeypatch):
    import olive.prompt_ui as pui
    pui._command_lookup.clear()
    pui.register_commands({':exit': lambda: None})
    comp = pui.OliveCompleter()
    doc = MagicMock(text_before_cursor=':ex')
    ev = MagicMock()
    completions = list(comp.get_completions(doc, ev))
    found = False
    for c in completions:
        display = getattr(c, 'display', '')
        if hasattr(display, '__iter__'):
            if any(':exit' in str(t[1]) for t in display):
                found = True
        if getattr(c, 'text', '') == ':exit':
            found = True
    assert found

def test_olive_completer_shell(monkeypatch):
    monkeypatch.setattr('olive.prompt_ui.get_available_shell_commands', lambda: ['ls'])
    comp = pui.OliveCompleter()
    doc = MagicMock(text_before_cursor='!l')
    ev = MagicMock()
    completions = list(comp.get_completions(doc, ev))
    assert any('ls' in c.text for c in completions)

def test_olive_completer_at(monkeypatch):
    comp = pui.OliveCompleter()
    doc = MagicMock(text_before_cursor='@')
    ev = MagicMock()
    with patch('prompt_toolkit.completion.PathCompleter.get_completions', return_value=[MagicMock(text='file.txt', display='file.txt')]):
        completions = list(comp.get_completions(doc, ev))
        # No assertion here—just exercise the path branch

def test_handle_ctrl_c_buffer_clears(monkeypatch):
    buf = MagicMock(text='data')
    app = MagicMock(current_buffer=buf, layout=MagicMock())
    event = MagicMock(app=app)
    monkeypatch.setattr('olive.prompt_ui._last_ctrl_c_time', [0])
    monkeypatch.setattr('olive.prompt_ui._ctrlc_hint_active', [False])
    with patch('builtins.print') as bp:
        pui.handle_ctrl_c(event)
        bp.assert_called()

def test_handle_ctrl_c_double_exit(monkeypatch):
    import olive.prompt_ui as pui
    from unittest.mock import MagicMock, patch

    class FakeBuffer:
        def __init__(self):
            self.cleared = False
        @property
        def text(self):
            if not self.cleared:
                return "not empty"
            class StrObj(str):
                def strip(self_nonstd):
                    return ""
            return StrObj("")
        def reset(self):
            self.cleared = True

    buf = FakeBuffer()
    app = MagicMock(current_buffer=buf, layout=MagicMock())
    event = MagicMock(app=app)

    # Simulate first Ctrl+C with non-empty buffer
    pui._last_ctrl_c_time[0] = 0.0
    pui._ctrlc_hint_active[0] = False
    monkeypatch.setattr('olive.prompt_ui.time', MagicMock(time=lambda: 1.0))
    with patch('olive.shell.admin.perform_graceful_exit') as pge:
        pui.handle_ctrl_c(event)  # First press: buffer clears, timer set
        # Second press, buffer is empty and within double-tap window
        monkeypatch.setattr('olive.prompt_ui.time', MagicMock(time=lambda: 1.5))
        pui.handle_ctrl_c(event)
        assert pge.called

def test_insert_newline():
    event = MagicMock()
    pui.insert_newline(event)
    event.app.current_buffer.insert_text.assert_called_with('\n')

def test_submit():
    event = MagicMock()
    pui.submit(event)
    event.app.current_buffer.validate_and_handle.assert_called()

def test_force_submit():
    event = MagicMock()
    pui.force_submit(event)
    event.app.current_buffer.validate_and_handle.assert_called()
