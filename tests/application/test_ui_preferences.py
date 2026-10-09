"""Preference restoration uses canonical commands and backend revision ownership."""

from dataclasses import dataclass
from threading import Event

import pytest


@dataclass(frozen=True)
class PreferenceResult:
    """Injected outer I/O completion, independent of any GUI implementation."""

    parent: str | None = None
    feedback: str | None = None


def test_stale_guard_is_atomic_and_emits_no_effects_or_feedback(tmp_path):
    from brz2obsidian.application.contracts import SetDestination
    from brz2obsidian.application.operations import ApplicationSession

    session = ApplicationSession()
    original_revision = session.snapshot.revision
    update = session.dispatch(
        SetDestination(parent_or_null=str(tmp_path / "new"), vault_name="Edited")
    )
    stale = session.dispatch_if_current(
        SetDestination(parent_or_null=str(tmp_path / "old"), vault_name=""),
        original_revision,
    )
    assert stale.snapshot == update.snapshot
    assert stale.effects == ()


@pytest.mark.parametrize("revision", [True, -1, "0", 0.0, None])
def test_revision_guard_rejects_invalid_shapes_without_state_change(revision):
    from brz2obsidian.application.contracts import SimpleCommand
    from brz2obsidian.application.operations import ApplicationSession

    session = ApplicationSession()
    before = session.snapshot
    with pytest.raises(ValueError):
        session.dispatch_if_current(SimpleCommand(command="request_close"), revision)
    assert session.snapshot == before


def test_changed_parent_emits_canonical_effect_but_name_edits_do_not(tmp_path):
    from brz2obsidian.application.contracts import SetDestination
    from brz2obsidian.application.operations import ApplicationSession

    session = ApplicationSession()
    initial = session.dispatch_if_current(
        SetDestination(parent_or_null=str(tmp_path), vault_name="First"), 0
    )
    effects = [e for e in initial.effects if e.effect == "persist_output_parent"]
    assert len(effects) == 1 and effects[0].path == str(tmp_path)
    changed_name = session.dispatch(
        SetDestination(parent_or_null=str(tmp_path), vault_name="Second")
    )
    assert not any(e.effect == "persist_output_parent" for e in changed_name.effects)
    cleared = session.dispatch(SetDestination(parent_or_null=None, vault_name="Second"))
    assert not any(e.effect == "persist_output_parent" for e in cleared.effects)


def test_blocked_startup_preferences_cannot_overwrite_newer_input(tmp_path):
    from brz2obsidian.application.contracts import SetDestination
    from brz2obsidian.application.runner import HostRunner

    loading, release, edited, delivered = Event(), Event(), Event(), Event()
    updates = []

    class Preferences:
        def load(self):
            loading.set()
            assert release.wait(5)
            return PreferenceResult(parent=str(tmp_path / "old"))

        def save(self, parent):
            return PreferenceResult(parent=parent)

    def observed(prepared):
        updates.append(prepared.update.snapshot)
        if len(updates) == 1:
            edited.set()
        else:
            delivered.set()

    runner = HostRunner(None, observed, lambda page: None, preferences=Preferences())
    try:
        runner.restore_preferences()
        assert loading.wait(2)
        runner.submit(
            SetDestination(parent_or_null=str(tmp_path / "new"), vault_name="")
        )
        assert edited.wait(2)  # Command delivery precedes release of blocked I/O.
        release.set()
        assert delivered.wait(2)
        assert runner.session.snapshot.parent == str(tmp_path / "new")
    finally:
        release.set()
        runner.shutdown()


def test_parent_saves_are_ordered_and_stale_failure_does_not_replace_feedback(tmp_path):
    from brz2obsidian.application.contracts import SetDestination
    from brz2obsidian.application.runner import HostRunner

    started, release, edited, saved = Event(), Event(), Event(), Event()
    writes, feedback = [], []

    class Preferences:
        def save(self, parent):
            writes.append(parent)
            if parent.endswith("old"):
                started.set()
                assert release.wait(5)
                return PreferenceResult(feedback="Old save failed.")
            saved.set()
            return PreferenceResult(parent=parent)

    runner = HostRunner(
        None,
        lambda prepared: (
            edited.set()
            if prepared.update.snapshot.parent == str(tmp_path / "new")
            else None
        ),
        lambda page: None,
        preferences=Preferences(),
        on_feedback=feedback.append,
    )
    try:
        runner.submit(
            SetDestination(parent_or_null=str(tmp_path / "old"), vault_name="")
        )
        assert started.wait(2)
        runner.submit(
            SetDestination(parent_or_null=str(tmp_path / "new"), vault_name="")
        )
        assert edited.wait(2)
        release.set()
        assert saved.wait(2)
        barrier = Event()
        runner.submit_if_current(
            SetDestination(parent_or_null=str(tmp_path / "new"), vault_name=""),
            runner.session.snapshot.revision,
            on_complete=lambda update: barrier.set(),
        )
        assert barrier.wait(2)
        assert writes == [str(tmp_path / "old"), str(tmp_path / "new")]
        assert feedback == []
    finally:
        release.set()
        runner.shutdown()
