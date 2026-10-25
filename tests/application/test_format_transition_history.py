"""Public maintenance persistence shares existing SOURCE/LOCAL review storage."""

import hashlib
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

from brz2obsidian.application.checkpoint_contracts import CheckpointResult
from brz2obsidian.core import load_review, save_review
from tests.application.test_format_transition import transition_case
from tests.reconciliation.test_resolution import action
from tests.support.recorded_format6 import CURRENT, FIXTURE, NOTE, ORIGINAL


def test_format_transition_save_load_resume_keeps_old_identity_and_explicit_current(tmp_path, monkeypatch):
    operations, vault, history = transition_case(tmp_path, monkeypatch)
    monkeypatch.setattr(operations, "inspect_update_inputs", lambda path: nullcontext(SimpleNamespace(
        history=history, read_payload=lambda **kwargs: operations.read_checkpoint_payload(path, **kwargs),
        inspect=lambda **kwargs: operations.inspect_history(path, **kwargs))))
    offered = operations.prepare_format_transition(vault, FIXTURE / "source.brz")
    assert offered.preparation is not None, offered
    note = next(c for c in offered.preparation.review.proposal.changes if c.item_id == "5f71e626-527e-47b4-abaa-e53d124619f8")
    kept = operations.resolve_update(offered.preparation, action(offered.preparation.review, note,
        domain="format", choice="current", decision_id="keep-legacy-current"))
    assert kept.code == "accepted", kept
    original_rows = history.checkpoint.manifest.source

    def capture(current_vault, old_source, **request):
        assert current_vault == str(vault)
        assert request["identity"].output_format == 6 and request["identity"].profile_version == "9"
        assert request["review"].facts.format_operation.kind == "format_transition"
        assert request["source_binding"].incoming_identity.output_format == 7
        assert {p.relative_to(old_source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in Path(old_source).rglob("*") if p.is_file()} == {r.path:r.sha256 for r in original_rows}
        assert (Path(old_source) / NOTE).read_bytes() == ORIGINAL
        assert operations.observe_reviewed_source(request["review_source"], request["review"]) == request["source_binding"]
        loaded = load_review(save_review(request["review"]).record)
        assert loaded.status == "loaded"
        locator = history.checkpoint.locator.model_copy(update={"commit": "c" * 40, "generation": 2})
        history.checkpoint = SimpleNamespace(status="valid", locator=locator, review=loaded.loaded,
            manifest=SimpleNamespace(boundary="local", identity=request["identity"], source=original_rows,
                reviewed_source=request["source_binding"], observed_source=request["observed_source"]))
        return CheckpointResult(schema_id="brz2obsidian.checkpoint-result", schema_version=1,
            status="captured", code="captured", commit=locator.commit, ref=locator.association.ref,
            history_retained=True, objects_written=True, object_storage="verified",
            authored_files_changed=False, message="Captured via the controlled public history port", locator=locator)

    monkeypatch.setattr(operations, "capture_checkpoint", capture)
    saved = operations.save_update(kept.preparation)
    assert saved.kind == "format_transition" and saved.code == "saved", saved
    assert saved.checkpoint.commit == "c" * 40
    loaded = operations.load_update(vault)
    assert loaded.kind == "format_transition" and loaded.loaded is not None and not loaded.ready
    assert not loaded.loaded.ready
    resumed = operations.resume_update(vault)
    assert resumed.kind == "format_transition" and resumed.preparation is not None, resumed
    assert resumed.generation == 1 and not resumed.ready
    assert [a.decision_id for a in resumed.preparation.review.approvals] == ["keep-legacy-current"]
    assert resumed.preparation.review.facts.baseline_identity.output_format == 6
    current = next(s for s in resumed.preparation.review.facts.subjects if s.item_id == note.item_id)
    assert current.baseline.content.data == ORIGINAL and current.current.content.data == CURRENT
    assert (vault / NOTE).read_bytes() == CURRENT
