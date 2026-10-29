"""Saved resume and onboarding reobservation report their own retired slots."""

from pathlib import Path
from uuid import uuid4

import pytest

from brz2obsidian.application.update_contracts import UpdatePreparation
from brz2obsidian.application.update_facts import assemble_facts
from brz2obsidian.core import load_review, prepare_review, save_review
from tests.application.test_update_lifecycle_admission import note
from tests.application.test_update_stale_counts import GUIDE, NOTE, refresh_case
from tests.reconciliation.test_resolution import action


def persisted_inputs(case):
    saved = save_review(case.prepared.review)
    assert saved.status == "saved"
    loaded = load_review(saved.record)
    assert loaded.status == "loaded"

    class PersistedInputs(type(case.operations)):
        def inspect_history(self, *args, **kwargs):
            history = super().inspect_history(*args, **kwargs)
            history.checkpoint.review = loaded.loaded
            history.admission.inventory_complete = True
            return history

    case.operations = PersistedInputs()


def test_saved_resume_counts_only_invalidated_second_and_retains_guide(
    tmp_path, request
):
    case = refresh_case(tmp_path, request)
    guide = next(
        a
        for a in case.prepared.review.approvals
        if a.decision_id == "accepted:" + GUIDE
    )
    persisted_inputs(case)
    case.current[NOTE] = note("Later Second writing.")
    result = case.operations.resume_update(case.prepared.vault)
    assert result.preparation is not None, result.code
    assert not result.ready and result.unresolved == 1
    assert result.stale == 1
    assert result.preparation.review.approvals == (guide,)
    assert guide.result.data == b"Authored Guide.\n"
    assert result.publication == "not_started" and result.application is None


def test_unknown_original_onboarding_reobservation_counts_reopened_second_only(
    tmp_path, request
):
    case = refresh_case(tmp_path, request)
    incoming = {
        s.path: s.incoming.data
        for s in case.prepared.review.facts.subjects
        if s.incoming is not None
    }
    facts = assemble_facts(
        incoming,
        incoming,
        case.current,
        proposal_id="review:onboarding-slots",
        generation=1,
        originals_known=False,
        onboarding=True,
    )
    plan = prepare_review(facts, preflight=case.checks)
    binding = case.operations.observe_reviewed_source(
        Path(case.prepared.payload_directory), plan
    )
    prepared = UpdatePreparation.model_validate(
        case.prepared.model_dump()
        | {
            "kind": "onboarding",
            "review": plan,
            "source_binding": binding,
        }
    )
    for requirement in tuple(prepared.review.requirements):
        assert requirement.domain == "format"
        change = next(
            c
            for c in prepared.review.proposal.changes
            if c.change_id == requirement.change_id
        )
        chosen = case.operations.resolve_update(
            prepared,
            action(
                prepared.review,
                change,
                domain="format",
                choice="current",
                decision_id="onboarding:" + change.path,
            ),
        )
        assert chosen.code == "accepted", chosen.code
        prepared = chosen.preparation
    assert prepared.review.ready
    case.prepared, case.binding = prepared, binding
    guide = next(
        a for a in prepared.review.approvals if a.decision_id == "onboarding:" + GUIDE
    )
    retained = tuple(
        a for a in prepared.review.approvals if a.decision_id != "onboarding:" + NOTE
    )
    persisted_inputs(case)
    case.current[NOTE] = note("Later onboarding Second writing.")
    result = case.operations.refresh_update(prepared)
    assert result.preparation is not None, result.code
    assert result.kind == "onboarding" and not result.ready
    assert result.stale == result.unresolved == 1
    assert result.preparation.review.approvals == retained
    assert guide.result.data == b"Authored Guide.\n"
    assert all(
        s.baseline.status == "unknown" for s in result.preparation.review.facts.subjects
    )
    assert result.publication == "not_started" and result.application is None


@pytest.mark.parametrize("command", ("save", "apply"))
def test_closed_save_apply_harmless_retirement_stops_known_and_retains_ready_plan(
    tmp_path, request, command
):
    from brz2obsidian.application.update_context import UpdateContext
    from tests.application.test_update_context import worker_context_call

    case = refresh_case(tmp_path, request, flat=True)
    context = UpdateContext(operations=case.operations)
    opened = worker_context_call(
        context,
        {
            "command": "prepare",
            "kind": "source_update",
            "source": str(tmp_path / "controlled.brz"),
            "vault": case.prepared.vault,
            "selection_id": str(uuid4()),
        },
    )
    assert opened.ready and opened.binding is not None
    case.current[NOTE] = case.note("Incoming Second.")
    stopped = worker_context_call(
        context, {"command": command, "binding": opened.binding}
    )
    assert stopped.status == "stale_review" and stopped.code == "current_facts_changed"
    assert not stopped.ready and stopped.stale == stopped.unresolved == 0
    assert stopped.publication == "not_started" and stopped.history_retained is True
    assert stopped.checkpoint_commit == opened.checkpoint_commit
    assert (
        stopped.capture is None
        and stopped.operation is None
        and stopped.binding is not None
    )
    page = worker_context_call(context, {"command": "page", "binding": stopped.binding})
    assert page.status == "available"
    second = next(row for row in page.page.items if row.current_path == NOTE)
    assert (
        second.current
        == second.incoming
        == second.result
        == case.note("Incoming Second.")
    )
    guide = next(row for row in page.page.items if row.current_path == GUIDE)
    assert guide.result == b"Authored Guide.\n"
    refreshed = worker_context_call(
        context, {"command": "refresh", "binding": stopped.binding}
    )
    assert refreshed.ready and refreshed.status == "prepared_review"
    assert refreshed.stale == refreshed.unresolved == 0
    assert (
        refreshed.publication == "not_started"
        and refreshed.capture is None
        and refreshed.operation is None
    )
