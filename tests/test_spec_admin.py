import pytest
from olive.canonicals.spec.models import FeatureSpec
from olive.tools.spec import admin as spec_admin
from olive.tools.spec.state import set_active_spec_id, get_active_spec_id


# --- Utilities ---
def setup_specs(tmp_path, ids_titles):
    """Utility: create dummy spec files and return their IDs, using tmp_path as specs dir."""
    specs = []
    for sid, title in ids_titles:
        # Use the real create, but patch the id to match the test's expected value
        spec = FeatureSpec.create(
            title=title,
            description=f"Desc for {title}",
            specs_dir=tmp_path,
            suppress_git=True,
        )
        # Patch id and filename to match test expectations
        if spec.id != sid:
            # Remove the file with the auto-generated ID
            (tmp_path / f"{spec.id}.yml").unlink(missing_ok=True)
            # Override the ID, then save under the desired ID
            spec.id = sid
            spec.save(specs_dir=tmp_path)
        specs.append(spec)
    return specs


@pytest.mark.skip(reason="Sandbox/admin commands not ready for testing")
def test_specs_list_and_detail(tmp_path, monkeypatch, capsys):
    ids_titles = [("20250101_000001", "Spec A"), ("20250101_000002", "Spec B")]
    setup_specs(tmp_path, ids_titles)
    set_active_spec_id("20250101_000001")

    res = spec_admin.specs_list_command()
    captured = capsys.readouterr()
    assert ">> Active" in captured.out
    assert "Spec A" in captured.out and "Spec B" in captured.out

    detail = spec_admin.spec_detail_command("20250101_000001")
    captured = capsys.readouterr()
    assert isinstance(detail, FeatureSpec)
    assert detail.title == "Spec A"

    # Partial ID (should resolve to Spec B)
    detail_partial = spec_admin.spec_detail_command("000002")
    captured = capsys.readouterr()
    assert isinstance(detail_partial, FeatureSpec)
    assert detail_partial.title == "Spec B"


@pytest.mark.skip(reason="Sandbox/admin commands not ready for testing")
def test_specs_list_empty(tmp_path, capsys):
    """Spec list handles no specs gracefully."""
    _ = spec_admin.specs_list_command()
    captured = capsys.readouterr()
    assert "no specs" in captured.out.lower() or "none found" in captured.out.lower()


@pytest.mark.skip(reason="Sandbox/admin commands not ready for testing")
def test_spec_detail_not_found(tmp_path, capsys):
    """Detail shows error for missing/unknown ID."""
    _ = spec_admin.spec_detail_command("doesnotexist")
    captured = capsys.readouterr()
    assert (
        "not found" in captured.out.lower() or "no specs found" in captured.out.lower()
    )


@pytest.mark.skip(reason="Sandbox/admin commands not ready for testing")
def test_spec_delete_confirmation(monkeypatch, tmp_path, capsys):
    ids_titles = [("20250101_000003", "Spec C")]
    setup_specs(tmp_path, ids_titles)
    # Simulate "n" input
    monkeypatch.setattr("builtins.input", lambda _: "n")
    _ = spec_admin.spec_delete_command("20250101_000003")
    captured = capsys.readouterr()
    assert "cancelled" in captured.out.lower()
    # Simulate "y" input for next test
    setup_specs(tmp_path, ids_titles)


@pytest.mark.skip(reason="Sandbox/admin commands not ready for testing")
def test_spec_delete_force(tmp_path):
    ids_titles = [("20250101_000001", "Spec A")]
    setup_specs(tmp_path, ids_titles)
    deleted = spec_admin.spec_delete_command("20250101_000001 -f")
    assert isinstance(deleted, FeatureSpec)
    assert deleted.id == "20250101_000001"

    ids_titles = [("20250101_000004", "Spec D")]
    setup_specs(tmp_path, ids_titles)
    deleted = spec_admin.spec_delete_command("20250101_000004 -f")
    assert isinstance(deleted, FeatureSpec)
    assert deleted.id == "20250101_000004"


@pytest.mark.skip(reason="Sandbox/admin commands not ready for testing")
def test_spec_delete_active_unsets(tmp_path):
    ids_titles = [("20250101_000001", "Spec A")]
    setup_specs(tmp_path, ids_titles)
    set_active_spec_id("20250101_000001")
    deleted = spec_admin.spec_delete_command("20250101_000001 -f")
    assert isinstance(deleted, FeatureSpec)
    assert deleted.id == "20250101_000001"
    # Should now be unset
    assert get_active_spec_id() is None
    ids_titles = [("20250101_000005", "Spec E")]
    setup_specs(tmp_path, ids_titles)


@pytest.mark.skip(reason="Sandbox/admin commands not ready for testing")
def test_spec_delete_not_found(tmp_path, capsys):
    _ = spec_admin.spec_delete_command("no_such_spec -f")
    captured = capsys.readouterr()
    assert (
        "not found" in captured.out.lower() or "no spec found" in captured.out.lower()
    )


@pytest.mark.skip(reason="Sandbox/admin commands not ready for testing")
def test_set_active_success_and_ambiguous(tmp_path, capsys):
    ids_titles = [("20250101_000001", "Spec A"), ("20250101_000002", "Spec B")]
    setup_specs(tmp_path, ids_titles)
    # Set by full ID
    res = spec_admin.spec_set_active_command("20250101_000001")
    assert isinstance(res, FeatureSpec)
    assert res.id == "20250101_000001"

    # Set by partial (should succeed if unique)
    res_partial = spec_admin.spec_set_active_command("000002")
    assert isinstance(res_partial, FeatureSpec)
    assert res_partial.id == "20250101_000002"
    # Ambiguous partial (should print error and return None)
    res_ambiguous = spec_admin.spec_set_active_command("00000")
    captured = capsys.readouterr()
    assert res_ambiguous is None
    assert (
        "ambiguous" in captured.out.lower()
        or "not found" in captured.out.lower()
        or "no spec found" in captured.out.lower()
    )

    # Unknown ID
    res_unknown = spec_admin.spec_set_active_command("doesnotexist")
    captured = capsys.readouterr()
    assert res_unknown is None
    assert (
        "not found" in captured.out.lower() or "no spec found" in captured.out.lower()
    )

    # Ambiguous partial (again)
    _ = spec_admin.spec_set_active_command("0000")
    captured = capsys.readouterr()
    assert "no spec found matching id '0000'" in captured.out.lower() or "not found" in captured.out.lower()


@pytest.mark.skip(reason="Sandbox/admin commands not ready for testing")
def test_command_registration():
    import olive  # noqa
    from olive.tools import tool_registry
    tool_registry.discover_all()
    from olive.prompt_ui import get_management_commands
    from olive.prompt_ui import get_management_commands

    cmds = get_management_commands()
    assert ":specs" in cmds
    assert ":spec" in cmds
    assert ":spec delete" in cmds
    assert ":spec set-active" in cmds


@pytest.mark.skip(reason="Sandbox/admin commands not ready for testing")
def test_lossless_yaml_roundtrip(tmp_path):
    spec = FeatureSpec.create(
        "Roundtrip Spec", "desc", specs_dir=tmp_path, suppress_git=True
    )
    spec.save(specs_dir=tmp_path)
    loaded = FeatureSpec.load(spec.id, specs_dir=tmp_path)
    assert loaded.title == spec.title
    assert loaded.description == spec.description


@pytest.mark.skip(reason="Sandbox/admin commands not ready for testing")
def test_deleting_last_spec_leaves_list_empty(tmp_path, capsys):
    ids_titles = [("20250101_000001", "Spec A")]
    setup_specs(tmp_path, ids_titles)
    deleted = spec_admin.spec_delete_command("20250101_000001 -f")
    assert isinstance(deleted, FeatureSpec)
    _ = spec_admin.specs_list_command()
    captured = capsys.readouterr()
    assert "no specs" in captured.out.lower() or "none found" in captured.out.lower()


@pytest.mark.skip(reason="Sandbox/admin commands not ready for testing")
def test_partial_id_prefers_exact(tmp_path, capsys):
    ids_titles = [("20250101_000001", "Spec A"), ("20250101_000002", "Spec B")]
    setup_specs(tmp_path, ids_titles)
    # Exact match should win
    res = spec_admin.spec_detail_command("20250101_000001")
    assert isinstance(res, FeatureSpec)
    assert res.id == "20250101_000001"
    # Ambiguous partial returns None and prints error
    res_ambig = spec_admin.spec_detail_command("00000")
    captured = capsys.readouterr()
    assert res_ambig is None
    assert (
        "ambiguous" in captured.out.lower()
        or "not found" in captured.out.lower()
        or "no spec found" in captured.out.lower()
    )


@pytest.mark.skip(reason="Sandbox/admin commands not ready for testing")
def test_yaml_validity_on_modify(tmp_path):
    spec = FeatureSpec.create("ModSpec", "descX", specs_dir=tmp_path, suppress_git=True)
    spec.save(specs_dir=tmp_path)
    loaded = FeatureSpec.load(spec.id, specs_dir=tmp_path)
    loaded.title = "Changed"
    loaded.save(specs_dir=tmp_path)
    again = FeatureSpec.load(spec.id, specs_dir=tmp_path)
    assert again.title == "Changed"
