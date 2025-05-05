import pytest
from unittest.mock import patch, MagicMock
import olive.context.utils as utils

import pytest
from olive.context import context
from olive.context.utils import safe_add_extra_context_file, safe_remove_extra_context_file
from pathlib import Path

import olive.env

def test_safe_add_extra_context_file_success(tmp_path):
    old_root = olive.env.get_project_root()
    olive.env.set_project_root(tmp_path)
    test_file = tmp_path / "hello.txt"
    test_file.write_text("abc\ndef")
    safe_remove_extra_context_file(str(test_file))
    assert safe_add_extra_context_file(str(test_file))
    safe_remove_extra_context_file(str(test_file))
    olive.env.set_project_root(old_root)

def test_safe_add_extra_context_file_excluded(tmp_path, monkeypatch):
    test_file = tmp_path / "exclude.txt"
    test_file.write_text("abc")
    monkeypatch.setattr(context, "is_file_excluded", lambda p: True)
    assert not safe_add_extra_context_file(str(test_file), force=False)
    assert safe_add_extra_context_file(str(test_file), force=True)
    safe_remove_extra_context_file(str(test_file))

def test_safe_remove_extra_context_file_success(tmp_path):
    test_file = tmp_path / "remove.txt"
    test_file.write_text("123")
    safe_add_extra_context_file(str(test_file))
    assert safe_remove_extra_context_file(str(test_file))
    assert safe_remove_extra_context_file(str(test_file))

def test_safe_remove_extra_context_file_notfound(tmp_path):
    test_file = tmp_path / "notfound.txt"
    test_file.write_text("doesn't matter")
    assert safe_remove_extra_context_file(str(test_file))

def test_get_git_diff_stats(monkeypatch):
    monkeypatch.setattr('subprocess.run', lambda *a, **k: MagicMock(stdout='1\t2\tfile.py\n'))
    stats = utils.get_git_diff_stats()
    assert 'file.py' in stats

def test_render_file_context_for_llm_raw(monkeypatch):
    ctx = MagicMock()
    ctx.state.files = [MagicMock(path='a.py', lines=['a', 'b'])]
    ctx.state.extra_files = []
    ctx.state.metadata = {}
    monkeypatch.setattr('olive.context.utils.context', ctx)
    prefs = MagicMock(is_abstract_mode_enabled=lambda: False)
    monkeypatch.setattr('olive.context.utils.get_prefs_lazy', lambda: prefs)
    monkeypatch.setattr('olive.context.utils.get_logger', lambda _: MagicMock(info=lambda *a, **k: None))
    out = utils.render_file_context_for_llm()
    assert any('file:' in o for o in out)
