import pytest
from unittest.mock import patch, MagicMock
from olive.context.__init__ import OliveContext

def test_load_and_save(monkeypatch, tmp_path):
    ctx_file = tmp_path / 'active.json'
    monkeypatch.setattr('olive.context.__init__.CONTEXT_PATH', ctx_file)
def test_load_and_save(monkeypatch, tmp_path, reset_olive_context):
    ctx_file = tmp_path / 'active.json'
    monkeypatch.setattr('olive.context.__init__.CONTEXT_PATH', ctx_file)
    ctx = OliveContext()
    ctx.state.chat = []
    ctx.save()
    assert ctx_file.exists()
    ctx2 = OliveContext()
def test_reset(monkeypatch, tmp_path, reset_olive_context):
    ctx_file = tmp_path / 'active.json'
    monkeypatch.setattr('olive.context.__init__.CONTEXT_PATH', ctx_file)
    ctx = OliveContext()
    ctx.state.chat = [MagicMock(role='user', content='hi')]
    ctx.save()
    ctx.reset()
    assert ctx.state.chat == []

    ctx.reset()
    assert ctx.state.chat == []

def test_append_chat():
    ctx = OliveContext()
    ctx.state.chat = []
    ctx.append_chat('user', 'hello')
    assert ctx.state.chat[-1].role == 'user'

def test_inject_system_message(monkeypatch):
    ctx = OliveContext()
    monkeypatch.setattr('olive.context.__init__.injection.append_context_injection', lambda content: 'ok')
    assert ctx.inject_system_message('sys') == 'ok'

def test_add_and_remove_extra_file():
    ctx = OliveContext()
    ctx.state.extra_files = []
    ctx.add_extra_file('/tmp/f', ['a', 'b'])
    assert ctx.state.extra_files[0].path.endswith('/tmp/f')
    removed = ctx.remove_extra_file('/tmp/f')
    assert removed == 1

def test_add_metadata_and_imports():
    ctx = OliveContext()
    ctx.state.metadata = {}
    ctx.state.imports = {}
    ctx.add_metadata('a.py', [MagicMock()])
    ctx.add_imports('a.py', ['os'])
    assert 'a.py' in ctx.state.metadata
    assert 'a.py' in ctx.state.imports

def test_normalize_path(tmp_path):
    ctx = OliveContext()
    f = tmp_path / 'file.txt'
    f.write_text('hi')
    norm = ctx._normalize_path(str(f))
    assert norm.endswith('file.txt')

def test_hydrate(monkeypatch):
    ctx = OliveContext()
    monkeypatch.setattr(ctx, '_hydrate_base_system_prompt', lambda: None)
    monkeypatch.setattr('olive.context.__init__.injection.get_context_injections', lambda role='system': ['inj'])
    monkeypatch.setattr(ctx, '_build_context_payload', lambda: ['cf'])
    monkeypatch.setattr('olive.context.__init__.prefs', MagicMock(is_abstract_mode_enabled=lambda: False))
    ctx.state.system = ['sys']
    ctx.state.metadata = {'x': [1]}
    ctx.state.imports = {'x': [1]}
    ctx.hydrate()
    assert ctx.state.system[1] == 'inj'
    assert ctx.state.files == ['cf']
    assert ctx.state.metadata == {}

def test_is_file_excluded(monkeypatch):
    ctx = OliveContext()
    monkeypatch.setattr('olive.context.__init__.prefs', MagicMock(get=lambda *a, **k: [], is_abstract_mode_enabled=lambda: False))
    monkeypatch.setattr('olive.context.__init__.is_ignored_by_git', lambda path: False)
    assert not ctx.is_file_excluded('abc')

def test_to_dict():
    ctx = OliveContext()
    d = ctx.to_dict()
    assert isinstance(d, dict)
