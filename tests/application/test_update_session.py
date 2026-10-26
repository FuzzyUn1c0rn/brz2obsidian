"""Session reduction keeps content replies and review/publication truth distinct."""

import pytest

from brz2obsidian.application.contracts import WorkerResponse
from brz2obsidian.application.operations import ApplicationSession
from brz2obsidian.application.transport import Terminal
from brz2obsidian.application.update_context_contracts import (
    UpdateContextBinding,
    UpdateContextResult,
)


def terminal(request, result):
    return Terminal(
        phase="completed",
        response=WorkerResponse(
            operation="update", request_id=request.request_id, sequence=1, result=result
        ),
    )


def test_waiting_to_close_keeps_prepared_review_and_unknown_contact_truth(tmp_path):
    from uuid import uuid4

    session = ApplicationSession()
    selection = str(uuid4())
    vault = str(tmp_path / "vault")
    session.select_update(vault, selection_id=selection)
    request = session.start_update(
        {
            "command": "prepare",
            "vault": vault,
            "selection_id": selection,
            "kind": "onboarding",
            "source": None,
        }
    )
    active = session.update_snapshot
    assert active.close_options == ("continue", "background", "wait", "safe_stop")
    assert not session.request_update_close(
        "safe_stop", expected_revision=active.revision - 1
    )
    assert session.update_snapshot.close_disposition is None
    assert session.request_update_close("wait", expected_revision=active.revision)
    waiting = session.update_snapshot
    assert (
        waiting.active_request_id == request.request_id
        and waiting.close_disposition == "wait"
    )
    binding = UpdateContextBinding(
        context_id=str(uuid4()),
        selection_id=selection,
        vault=vault,
        association_id=None,
        proposal_id="review:unsaved",
        generation=1,
        revision=1,
    )
    prepared = UpdateContextResult(
        status="prepared_review",
        code="prepared",
        kind="onboarding",
        binding=binding,
        ready=False,
        unresolved=1,
        history_retained=False,
        publication="not_published",
    )
    state = session.complete_update(request.request_id, terminal(request, prepared))
    assert state.binding == binding and state.reply == prepared
    assert state.close_disposition is None and state.close_options == (
        "continue",
        "save",
        "discard",
    )
    assert not state.ready and not state.history_retained
    assert not session.request_update_close(
        "discard", expected_revision=waiting.revision
    )
    assert session.update_snapshot.binding == binding
    session.bind_update_worker("actual-child")
    unknown = session.update_contact_uncertain("actual-child")
    assert unknown.needs_inspection and unknown.publication == "unknown"
    assert unknown.binding is None and unknown.close_options == ("close",)
    assert session.request_update_close("close", expected_revision=unknown.revision)
    assert (
        session.update_snapshot.needs_inspection
        and session.update_snapshot.publication == "unknown"
    )


@pytest.mark.parametrize("reply", ("launch_failure", "unqualified_refusal"))
def test_session_keeps_prior_uncertainty_when_a_new_worker_cannot_launch(
    tmp_path, reply
):
    session = ApplicationSession()
    selection = "11111111-1111-4111-8111-111111111111"
    vault = str(tmp_path / "vault")
    session.select_update(vault, selection_id=selection)
    session.bind_update_worker("previous-child")
    uncertain = session.update_contact_uncertain("previous-child")
    assert uncertain.needs_inspection and uncertain.publication == "unknown"
    session.bind_update_worker("new-child")
    request = session.start_update(
        {"command": "history", "vault": vault, "selection_id": selection}
    )
    outcome = (
        Terminal(phase="not_started", code="launch_failure")
        if reply == "launch_failure"
        else terminal(
            request,
            UpdateContextResult(
                kind="history", status="refused", code="context_changed"
            ),
        )
    )
    state = session.complete_update(request.request_id, outcome)
    assert state.needs_inspection and state.publication == "unknown"
    assert (
        state.transport_phase == outcome.phase and state.transport_code == outcome.code
    )
    assert not state.ready and state.binding is None


def test_session_keeps_saved_summary_across_content_reply_and_rejects_stale_selection(
    tmp_path,
):
    session = ApplicationSession()
    vault = str(tmp_path / "vault")
    selection = "11111111-1111-4111-8111-111111111111"
    session.select_update(vault, selection_id=selection)
    request = session.start_update(
        {
            "command": "prepare",
            "vault": vault,
            "selection_id": selection,
            "kind": "source_update",
            "source": str(tmp_path / "reference.brz"),
        }
    )
    binding = UpdateContextBinding(
        context_id=selection,
        selection_id=selection,
        vault=vault,
        association_id="a" * 64,
        checkpoint_commit="b" * 40,
        checkpoint_generation=1,
        proposal_id="actual-proposal",
        generation=3,
        revision=1,
    )
    prepared = UpdateContextResult(
        status="prepared_review",
        code="prepared",
        kind="source_update",
        binding=binding,
        ready=True,
        changes=3,
        next_actions=("apply_update",),
        history_retained=True,
        checkpoint_commit="b" * 40,
    )
    session.complete_update(request.request_id, terminal(request, prepared))
    save = session.start_update({"command": "save", "binding": binding})
    saved_binding = binding.model_copy(
        update={
            "checkpoint_commit": "c" * 40,
            "checkpoint_generation": 2,
            "revision": 2,
        }
    )
    saved = prepared.model_copy(
        update={
            "code": "saved",
            "binding": saved_binding,
            "checkpoint_commit": "c" * 40,
        }
    )
    session.complete_update(save.request_id, terminal(save, saved))
    content = session.start_update(
        {"command": "choices", "binding": saved_binding, "limit": 1}
    )
    reply = UpdateContextResult(
        status="available",
        code="available",
        kind="source_update",
        binding=saved_binding,
    )
    session.complete_update(content.request_id, terminal(content, reply))
    state = session.update_snapshot
    assert state.ready and state.history_retained and state.changes == 3
    assert state.binding == saved_binding and state.checkpoint_commit == "c" * 40
    assert state.reply == reply
    edit = session.start_update(
        {
            "command": "begin_edit",
            "binding": saved_binding,
            "requirement_id": "actual-offer",
            "size": 4,
            "sha256": "d" * 64,
        }
    )
    draft_binding = saved_binding.model_copy(update={"revision": 3})
    draft = reply.model_copy(
        update={"code": "edit_started", "binding": draft_binding, "draft_pending": True}
    )
    session.complete_update(edit.request_id, terminal(edit, draft))
    assert not session.update_snapshot.ready and session.update_snapshot.draft_pending
    assert (
        session.update_snapshot.history_retained
        and session.update_snapshot.changes == 3
    )
    late = session.start_update(
        {"command": "choices", "binding": draft_binding, "limit": 1}
    )
    other = str(tmp_path / "other-vault")
    session.select_update(other, selection_id="22222222-2222-4222-8222-222222222222")
    session.complete_update(late.request_id, terminal(late, draft))
    state = session.update_snapshot
    assert state.vault == other and state.binding is None and not state.ready
    assert not state.history_retained and state.active_request_id is None
    assert state.last_operation_vault == vault and state.last_operation == draft
    assert session.snapshot.reviewed is None


def test_progress_is_observational_and_scoped_to_actual_request_selection_and_child(
    tmp_path,
):
    from brz2obsidian.application.update_stream import WorkerProgress
    from brz2obsidian.application.vault_progress_contracts import VaultProgress

    session = ApplicationSession()
    vault = str(tmp_path / "vault")
    selection = "11111111-1111-4111-8111-111111111111"
    session.select_update(vault, selection_id=selection)
    session.bind_update_worker("actual-child")
    requested = session.start_update(
        {
            "command": "prepare",
            "vault": vault,
            "selection_id": selection,
            "kind": "onboarding",
            "source": None,
        }
    )
    # The actual transport allocates sequence7; the host-created placeholder
    # sequence1 is not the stream's admission authority.
    actual = requested.model_copy(update={"sequence": 7})
    frame = WorkerProgress(
        request_id=actual.request_id,
        sequence=7,
        ordinal=1,
        elapsed_ms=123,
        value=VaultProgress(
            phase="publication",
            operation_id="a" * 32,
            operation_generation=9,
            intent_commit="b" * 40,
            completed_units=1,
            total_units=2,
            unit="files",
        ),
    )
    state = session.observe_update_progress("actual-child", actual, frame)
    assert state.progress == frame and state.progress.value.operation_generation == 9
    assert not state.ready and state.binding is None and not state.history_retained
    assert state.publication == "not_started" and state.next_actions == ()
    for epoch, request, observation in (
        ("old-child", actual, frame.model_copy(update={"ordinal": 2})),
        ("actual-child", actual, frame.model_copy(update={"sequence": 8})),
        ("actual-child", actual, frame.model_copy(update={"request_id": selection})),
    ):
        assert (
            session.observe_update_progress(epoch, request, observation).progress
            == frame
        )
    session.select_update(
        str(tmp_path / "other"), selection_id="22222222-2222-4222-8222-222222222222"
    )
    assert (
        session.observe_update_progress("actual-child", actual, frame).progress is None
    )
    session.complete_update(
        actual.request_id,
        terminal(
            actual,
            UpdateContextResult(
                kind="onboarding", status="refused", code="onboarding_evidence_required"
            ),
        ),
    )
    assert (
        session.update_snapshot.progress is None and not session.update_snapshot.ready
    )
