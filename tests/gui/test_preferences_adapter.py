"""Outer preference boundary: actual files, without a Qt dependency."""

import json


def test_new_launch_restores_only_output_parent(tmp_path):
    from brz2obsidian_ui.preferences import ParentPreferences

    store = ParentPreferences(tmp_path)
    assert store.load().parent is None
    assert store.save(str(tmp_path / "Sortie Café")).feedback is None
    fresh = ParentPreferences(tmp_path)
    assert fresh.load().parent == str(tmp_path / "Sortie Café")
    assert json.loads((tmp_path / "preferences.json").read_text("utf-8")) == {
        "output_parent": str(tmp_path / "Sortie Café")
    }


def test_corrupt_or_unavailable_preferences_have_safe_empty_default(tmp_path):
    from brz2obsidian_ui.preferences import ParentPreferences

    (tmp_path / "preferences.json").write_text('{"source":"BODY_CANARY"}', "utf-8")
    result = ParentPreferences(tmp_path).load()
    assert result.parent is None
    assert result.feedback and "BODY_CANARY" not in result.feedback
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("retained", "utf-8")
    result = ParentPreferences(blocked).load()
    assert result.parent is None and result.feedback
    assert ParentPreferences(blocked).save(str(tmp_path)).feedback
    assert blocked.read_text("utf-8") == "retained"


def test_failed_save_preserves_previous_parent(tmp_path, monkeypatch):
    from brz2obsidian_ui.preferences import ParentPreferences

    store = ParentPreferences(tmp_path)
    store.save(str(tmp_path / "first"))

    def denied(*args):
        raise PermissionError("PRIVATE_EXCEPTION_CANARY")

    monkeypatch.setattr("os.replace", denied)
    outcome = store.save(str(tmp_path / "second"))
    assert outcome.feedback and "PRIVATE_EXCEPTION_CANARY" not in outcome.feedback
    assert store.load().parent == str(tmp_path / "first")
    assert list(tmp_path.iterdir()) == [tmp_path / "preferences.json"]


def test_default_location_is_local_application_data(monkeypatch, tmp_path):
    from brz2obsidian_ui.preferences import application_data

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert application_data() == tmp_path / "brz2obsidian"
    monkeypatch.delenv("LOCALAPPDATA")
    assert application_data() is None


def test_transient_coordination_is_separate_from_preferences(monkeypatch, tmp_path):
    from brz2obsidian_ui.instance import coordination_directory
    from brz2obsidian_ui.preferences import application_data

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Preferences"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "Profile"))
    assert (
        coordination_directory() == tmp_path / "Profile/AppData/Local/Temp/brz2obsidian"
    )
    assert application_data() == tmp_path / "Preferences/brz2obsidian"
    monkeypatch.delenv("USERPROFILE")
    assert coordination_directory() is None
