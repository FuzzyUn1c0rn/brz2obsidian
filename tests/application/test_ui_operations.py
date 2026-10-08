from pathlib import Path

from brz2obsidian.application.operations import inspect


def test_inspection_returns_safe_planned_facts_and_complete_review(tmp_path):
    source = tmp_path / "Été archive.BRZ"
    source.write_bytes(
        (Path(__file__).parents[1] / "fixtures/minimal.brz").read_bytes()
    )
    before = source.read_bytes()
    result = inspect(source)
    assert result.status == "inspection_clean"
    assert result.counts.planned_notes == 1
    assert result.counts.actual_notes is None
    assert result.reviewed.source == str(source)
    assert result.reviewed.source_identity.source_sha256
    assert "publication" in result.pending
    assert "Authored body" not in result.model_dump_json()
    assert source.read_bytes() == before


def test_session_admission_review_invalidation_and_deferred_close(tmp_path):
    from brz2obsidian.application.contracts import (
        ApplyResult,
        InspectCommand,
        SelectSource,
        SimpleCommand,
    )
    from brz2obsidian.application.operations import ApplicationSession

    source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()
    session = ApplicationSession()
    selected = session.dispatch(SelectSource(path_or_null=str(source)))
    assert selected.snapshot.allowed_actions == ("inspect", "close")
    started = session.dispatch(InspectCommand())
    effect = started.effects[0]
    assert started.snapshot.busy_operation == "inspect"
    assert session.dispatch(InspectCommand()).effects == ()
    assert session.dispatch(
        SelectSource(path_or_null=str(tmp_path / "other.brz"))
    ).snapshot.source == str(source)
    assert session.dispatch(
        SimpleCommand(command="request_close")
    ).snapshot.close_pending
    done = session.dispatch(
        ApplyResult(
            request_id=effect.request.request_id,
            input_revision=effect.input_revision,
            result=inspect(source),
            process_status=0,
        )
    )
    assert done.snapshot.reviewed is not None
    assert done.effects[0].effect == "close_window"
    session.dispatch(SelectSource(path_or_null=str(tmp_path / "other.brz")))
    assert session.snapshot.reviewed is None
    assert session.snapshot.result is None


def test_host_retains_bounded_diagnostic_pages_after_worker_completion():
    from brz2obsidian.application.contracts import (
        ApplyResult,
        InspectCommand,
        SelectSource,
    )
    from brz2obsidian.application.operations import ApplicationSession

    source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()
    session = ApplicationSession()
    session.dispatch(SelectSource(path_or_null=str(source)))
    effect = session.dispatch(InspectCommand()).effects[0]
    result = inspect(source).model_copy(
        update={"diagnostic_text": "é" * 40000 + "\n" + "tail\n" * 120}
    )
    session.dispatch(
        ApplyResult(
            request_id=effect.request.request_id,
            input_revision=effect.input_revision,
            result=result,
            process_status=0,
        )
    )
    offset, text = 0, ""
    while True:
        page = session.diagnostics_page(offset, 100)
        assert len(page.text.encode("utf-8")) <= 32768
        assert len(page.lines) <= 100
        text += page.text
        if page.next_offset is None:
            break
        offset = page.next_offset
    assert text == result.diagnostic_text


def test_projection_excludes_raw_issue_evidence_and_reference_fragment_canaries():
    from brz2obsidian.application.operations import Operations
    from brz2obsidian.application.wiring import default_workflow
    from brz2obsidian.contracts import Issue

    source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()
    raw = default_workflow().inspect(source)

    class SourceBoundary:
        def inspect(self, path):
            return raw.model_copy(
                update={
                    "outcome": "warnings",
                    "issues": (
                        Issue(
                            code="invalid_reference",
                            phase="analysis",
                            severity="warning",
                            message="NOTE_BODY_CANARY",
                            guidance="REFERENCE_FRAGMENT_CANARY",
                            evidence=("RAW_EXCEPTION_CANARY",),
                        ),
                    ),
                }
            )

    result = Operations(SourceBoundary()).inspect(source)
    text = result.model_dump_json()
    assert result.status == "inspection_warnings"
    assert "invalid_reference" in text
    assert "CANARY" not in text
    assert "Authored body" not in text


def test_nested_safe_counts_and_review_are_immutable():
    import pytest
    from pydantic import ValidationError

    result = inspect((Path(__file__).parents[1] / "fixtures/minimal.brz").absolute())
    with pytest.raises(ValidationError):
        result.counts.planned_notes = 99
    with pytest.raises(ValidationError):
        result.reviewed.source_identity.source_sha256 = "changed"


def test_late_result_cannot_grant_review_for_wrong_revision():
    from brz2obsidian.application.contracts import (
        ApplyResult,
        InspectCommand,
        SelectSource,
    )
    from brz2obsidian.application.operations import ApplicationSession

    source = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()
    session = ApplicationSession()
    session.dispatch(SelectSource(path_or_null=str(source)))
    effect = session.dispatch(InspectCommand()).effects[0]
    done = session.dispatch(
        ApplyResult(
            request_id=effect.request.request_id,
            input_revision=effect.input_revision + 1,
            result=inspect(source),
            process_status=0,
        )
    )
    assert done.snapshot.result.status == "inspection_clean"
    assert done.snapshot.reviewed is None
    assert "convert_this_archive" not in done.snapshot.allowed_actions
