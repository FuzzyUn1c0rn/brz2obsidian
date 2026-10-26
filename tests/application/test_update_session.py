"""Session reduction keeps content replies and review/publication truth distinct."""

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
