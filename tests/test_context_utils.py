from unittest.mock import MagicMock


def test_safe_add_extra_context_file_success(tmp_path):
    import olive
    from olive.context.utils import (
        safe_add_extra_context_file,
        safe_remove_extra_context_file,
    )

    old_root = olive.env.get_project_root()
    olive.env.set_project_root(tmp_path)
    test_file = tmp_path / "hello.txt"
    test_file.write_text("abc\ndef")
    safe_remove_extra_context_file(str(test_file))
    assert safe_add_extra_context_file(str(test_file))
    safe_remove_extra_context_file(str(test_file))
    olive.env.set_project_root(old_root)


def test_safe_add_extra_context_file_excluded(tmp_path, monkeypatch):
    from olive.context.utils import (
        safe_add_extra_context_file,
        safe_remove_extra_context_file,
    )
    from olive.context import context

    context.reset()
    context.hydrate()
    test_file = tmp_path / "exclude.txt"
    test_file.write_text("abc")
    monkeypatch.setattr(context, "is_file_excluded", lambda p: True)
    assert not safe_add_extra_context_file(str(test_file), force=False)
    assert safe_add_extra_context_file(str(test_file), force=True)
    safe_remove_extra_context_file(str(test_file))


def test_safe_remove_extra_context_file_success(tmp_path):
    from olive.context.utils import (
        safe_add_extra_context_file,
        safe_remove_extra_context_file,
    )

    test_file = tmp_path / "remove.txt"
    test_file.write_text("123")
    safe_add_extra_context_file(str(test_file))
    assert safe_remove_extra_context_file(str(test_file))
    assert safe_remove_extra_context_file(str(test_file))


def test_safe_remove_extra_context_file_notfound(tmp_path):
    from olive.context.utils import safe_remove_extra_context_file

    test_file = tmp_path / "notfound.txt"
    test_file.write_text("doesn't matter")
    assert safe_remove_extra_context_file(str(test_file))


def test_get_git_diff_stats(monkeypatch):
    from olive.context import utils

    monkeypatch.setattr(
        "subprocess.run", lambda *a, **k: MagicMock(stdout="1\t2\tfile.py\n")
    )
    stats = utils.get_git_diff_stats()
    assert "file.py" in stats


def test_initialize_and_context_file_discovery(tmp_path, monkeypatch):
    """
    Ensure Olive can initialize in an arbitrary directory,
    and that its context discovers a hello.py file (and not unrelated files).
    """
    monkeypatch.chdir(tmp_path)

    from olive.init import initialize_olive
    from olive.context import OliveContext
    from pathlib import Path

    # Create a simple hello.py file in the temp directory
    hello_path = tmp_path / "hello.py"
    hello_path.write_text("print('hello world')\n")

    # Create a file that should NOT be picked up by context (e.g. .hidden, .txt, or in .olive)
    ignored_path = tmp_path / "ignored.sh"
    ignored_path.write_text("#!/bin/bash\n echo 'should not be included'")

    dot_olive_dir = tmp_path / ".olive"
    dot_olive_dir.mkdir()
    olive_internal = dot_olive_dir / "internal.py"
    olive_internal.write_text("print('internal')")

    # Initialize Olive in this directory
    initialize_olive()

    # Hydrate context, then check discovered files
    ctx = OliveContext()
    ctx.hydrate()
    ctx_files = ctx._discover_files()

    ctx_paths = {Path(p).as_posix().lstrip("./") for p in ctx_files}

    # 2. Define expectations
    required  = {"hello.py"}
    forbidden = {"ignored.txt", ".olive/internal.py"}

    # 3. Set-algebra checks
    missing  = required  - ctx_paths
    unwanted = ctx_paths & forbidden

    if missing:
        raise AssertionError(f"Missing required file(s): {missing}")
    if unwanted:
        raise AssertionError(f"Unexpected file(s) in context: {unwanted}")
    

def test_discover_files_includes_extra(tmp_path):
    from olive.context import OliveContext
    # Create a dummy file and add it as an extra file
    extra_file = tmp_path / "extra.txt"
    extra_file.write_text("foo\nbar\nbaz\n")
    ctx = OliveContext()
    ctx.add_extra_file(str(extra_file), ["foo\n", "bar\n", "baz\n"])
    files = ctx._discover_files(include_extra_files=True)
    # Should find the extra file by path
    assert any("extra.txt" in str(f) for f in files)
