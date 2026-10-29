"""A rejected offer reports the retained review without borrowing foreign authority."""

from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from brz2obsidian.application.update_context import UpdateContext
from brz2obsidian.application.update_session import UpdateSession
from tests.application.test_update_context import worker_context_call
from tests.application.test_update_stale_counts import GUIDE, NOTE, note, refresh_case
from tests.gui.update_worker_fixture import ReviewWorkerTransport


def refusal_case(tmp_path, request):
    case = refresh_case(tmp_path, request)
    case.current[NOTE] = note("Later Second writing.")
    refreshed = case.operations.refresh_update(case.prepared)
    assert refreshed.changes == 3 and refreshed.unresolved == 1 and refreshed.stale == 1
    assert not refreshed.ready and len(refreshed.preparation.review.approvals) == 1
    case.prepared = refreshed.preparation
    case.guide = case.prepared.review.approvals[0]
    assert case.guide.decision_id == "accepted:" + GUIDE and case.guide.result.data == b"Authored Guide.\n"
    case.source = tmp_path / "controlled.brz"
    case.source.write_bytes(b"Controlled preparation input")
    return case


def test_current_offer_refusal_preserves_closed_session_counts_choices_and_refresh(tmp_path, request):
    case = refusal_case(tmp_path, request)
    worker = ReviewWorkerTransport(case.operations)
    session = UpdateSession()
    session.select(case.prepared.vault, selection_id=str(uuid4()))

    def call(command, **values):
        operation = session.start({"command": command, **values})
        assert operation is not None
        return session.complete(operation.request_id, worker.run(operation))

    try:
        opened = call("prepare", kind="source_update", vault=case.prepared.vault,
                      source=str(case.source), selection_id=session.snapshot.selection_id)
        page = call("page", binding=opened.binding).reply
        second = next(row for row in page.page.items if row.current_path == NOTE)
        offer = next(row for row in page.offers if row.change_id == second.change_id)
        for requirement, digest in ((offer.requirement_id, "0" * 64), ("retired-offer", offer.assumptions_digest)):
            refused = call("choose", binding=opened.binding, requirement_id=requirement,
                           choice="current", assumptions_digest=digest)
            assert refused.reply.code == "offer_changed" and refused.reply.status == "refused"
            assert refused.changes == refused.reply.changes == 3
            assert refused.unresolved == refused.reply.unresolved == 1
            assert not refused.ready and not refused.reply.ready and refused.stale == 0
            assert refused.binding == opened.binding and not refused.needs_inspection
            assert refused.history_retained is True and refused.checkpoint_commit == opened.checkpoint_commit
            assert refused.publication == "not_started" and refused.reply.capture is None and refused.reply.operation is None
            assert "refresh_update" in refused.next_actions and "apply_update" not in refused.next_actions
        retained = call("page", binding=opened.binding).reply
        assert next(row for row in retained.page.items if row.current_path == GUIDE).result == b"Authored Guide.\n"
        assert next(row for row in retained.page.items if row.current_path == NOTE).result is None
        assert next(row for row in retained.offers if row.decision_id == case.guide.decision_id).selected == "current"
        assert session.snapshot.changes == 3 and session.snapshot.unresolved == 1
        assert "refresh_update" in session.snapshot.next_actions
        refreshed = call("refresh", binding=opened.binding)
        assert refreshed.binding is not None and refreshed.unresolved == 1 and not refreshed.ready
        assert refreshed.publication == "not_started" and refreshed.history_retained is True
    finally:
        worker.close()


def test_foreign_and_retired_choice_bindings_do_not_borrow_retained_plan(tmp_path, request):
    case = refusal_case(tmp_path, request)
    context = UpdateContext(operations=case.operations)
    opened = worker_context_call(context, {"command": "prepare", "kind": "source_update",
        "vault": case.prepared.vault, "source": str(case.source), "selection_id": str(uuid4())})
    current = worker_context_call(context, {"command": "refresh", "binding": opened.binding})
    assert current.binding.revision > opened.binding.revision
    for binding in (current.binding.model_copy(update={"context_id": str(uuid4())}), opened.binding):
        refused = worker_context_call(context, {"command": "choose", "binding": binding,
            "requirement_id": "retired-offer", "choice": "current", "assumptions_digest": "0" * 64})
        assert refused.code == "context_changed" and refused.binding is None
        assert refused.changes == refused.unresolved == 0 and not refused.ready
        assert "refresh_update" not in refused.next_actions and "apply_update" not in refused.next_actions
        assert refused.page is None and refused.offers == ()
    page = worker_context_call(context, {"command": "page", "binding": current.binding})
    assert page.page.total == 3
    assert next(row for row in page.page.items if row.current_path == GUIDE).result == b"Authored Guide.\n"
    worker_context_call(context, {"command": "close", "binding": current.binding, "choice": "discard"})


def test_pending_edit_keeps_its_guard_when_an_offer_is_refused(tmp_path, request):
    case = refusal_case(tmp_path, request)
    context = UpdateContext(operations=case.operations)
    opened = worker_context_call(context, {"command": "prepare", "kind": "source_update",
        "vault": case.prepared.vault, "source": str(case.source), "selection_id": str(uuid4())})
    page = worker_context_call(context, {"command": "page", "binding": opened.binding})
    second = next(row for row in page.page.items if row.current_path == NOTE)
    offer = next(row for row in page.offers if row.change_id == second.change_id)
    edit = worker_context_call(context, {"command": "begin_edit", "binding": opened.binding,
        "requirement_id": offer.requirement_id, "size": 3, "sha256": sha256(b"raw").hexdigest()})
    refused = worker_context_call(context, {"command": "choose", "binding": edit.binding,
        "requirement_id": offer.requirement_id, "choice": "current", "assumptions_digest": "0" * 64})
    assert refused.code == "uncommitted_draft" and refused.draft_pending and not refused.ready
    assert refused.binding == edit.binding
    assert refused.next_actions == ("continue_review", "discard_draft")
    assert refused.publication == "not_started" and refused.capture is None
    worker_context_call(context, {"command": "close", "binding": edit.binding, "choice": "discard"})


def test_source_refresh_guard_survives_a_current_bound_offer_refusal(tmp_path, monkeypatch):
    from brz2obsidian.application.checkpoint_contracts import CheckpointRead
    from tests.application.test_onboarding import legacy_inputs

    operations, vault, source, authored = legacy_inputs(tmp_path, monkeypatch)
    absent = CheckpointRead(schema_id="brz2obsidian.checkpoint-read", schema_version=1,
        status="absent", code="no_owned_checkpoint", locator=None, manifest=None, review=None,
        message="Controlled absent history")
    monkeypatch.setattr(operations, "read_checkpoint", lambda *args, **kwargs: absent)
    directories = []
    observe = operations.observe_reviewed_source
    def observing(directory, plan):
        directories.append(Path(directory))
        return observe(directory, plan)
    monkeypatch.setattr(operations, "observe_reviewed_source", observing)
    context = UpdateContext(operations=operations)
    opened = worker_context_call(context, {"command": "prepare", "kind": "onboarding",
        "vault": str(vault), "source": str(source), "selection_id": str(uuid4())})
    assert opened.binding is not None and opened.unresolved > 0
    (directories[-1] / "Home — Opening.md").write_bytes(b"Changed retained source bytes.\r\n")
    stale = worker_context_call(context, {"command": "page", "binding": opened.binding})
    assert stale.code == "source_payload_changed" and stale.next_actions == ("refresh_update",)
    refused = worker_context_call(context, {"command": "choose", "binding": opened.binding,
        "requirement_id": "retired-offer", "choice": "current", "assumptions_digest": "0" * 64})
    assert refused.code == "offer_changed" and not refused.ready
    assert refused.changes == opened.changes and refused.unresolved == opened.unresolved
    assert refused.next_actions == ("refresh_update",)
    assert refused.publication == "not_started" and not refused.history_retained
    assert refused.checkpoint_commit is None and refused.capture is None
    assert (vault / "Home — Opening.md").read_bytes() == authored
    worker_context_call(context, {"command": "close", "binding": opened.binding, "choice": "discard"})
