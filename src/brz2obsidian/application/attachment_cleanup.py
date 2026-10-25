"""Explicit retained attachment cleanup using the existing review lifecycle."""

from uuid import uuid4

from brz2obsidian.contracts import SourceIdentity
from brz2obsidian.core import prepare_review

from .update_contracts import UpdateResult
from .update_facts import output_identity, record
from .update_lifecycle import (
    _ExcludedDependency,
    _history,
    _materialize,
    _observed_facts,
    _prepared,
    _producer_memory,
    _read_source,
    _refused,
    _scoped,
)


def refused(code, history=None, *, action="inspect_history"):
    return _refused(code, history, action=action).model_copy(
        update={
            "kind": "attachment_cleanup",
            "recovery_gaps": history.admission.recovery_gaps if history else (),
        }
    )


def cleanup_facts(history, retained, *, observed, proposal_id, generation, source_memory=()):
    paths = tuple(row.path for row in history.admission.inventory)
    ownership = observed.read_attachment_ownership(locator=history.checkpoint.locator,
                                                   paths=paths) if paths else ()
    if any(proof.association_id != history.checkpoint.locator.association.association_id for proof in ownership):
        raise ValueError("Retained ownership has a different current association")
    facts = _observed_facts(
        history, retained, retained, proposal_id=proposal_id, generation=generation,
        source_memory=source_memory, retained_ownership=ownership,
    )
    return facts.model_copy(update={"format_operation": facts.format_operation.model_copy(
        update={"kind": "attachment_cleanup"}
    )})


def prepare_attachment_cleanup(operations, vault):
    """Obtain current native admission before reading retained or authored bytes."""
    try:
        with operations.inspect_update_inputs(vault) as observed:
            history = observed.history
            if history.admission.status == "recovery_first":
                return UpdateResult(
                    kind="attachment_cleanup",
                    status="recovery_required",
                    code="recovery_first",
                    next_actions=("review_recovery",),
                    history_retained=history.status == "intact",
                    recovery_gaps=history.admission.recovery_gaps,
                )
            if not history.admission.inventory_complete:
                return refused(
                    "reference_inventory_incomplete", history, action="review_tracking"
                )
            if any(
                row.excluded and row.path.lower().endswith(".md")
                for row in history.admission.inventory
            ):
                return refused(
                    "excluded_dependency_requires_tracking", history, action="review_tracking"
                )
            history, stopped = _history(operations, vault, observed)
            if stopped is not None:
                return stopped.model_copy(update={"kind": "attachment_cleanup"})
            retained = _read_source(operations, vault, history.checkpoint, observed)
            if output_identity(record(retained)) != history.checkpoint.manifest.identity:
                return refused("baseline_identity_mismatch", history)
            facts = cleanup_facts(
                history, retained, observed=observed, proposal_id=uuid4().hex, generation=1,
                source_memory=_producer_memory(history.checkpoint),
            )
            history = _scoped(operations, history, facts, observed=observed)
            review = prepare_review(facts, preflight=history.admission.preflight)
            directory = _materialize(retained)
            binding = operations.observe_reviewed_source(directory, review)
            return _prepared(
                history, directory, binding, review,
                SourceIdentity.model_validate(record(retained)["source_identity"]), True,
            )
    except _ExcludedDependency:
        return refused("excluded_dependency_requires_tracking", history, action="review_tracking")
    except OSError, ValueError, TypeError, AttributeError:
        return refused("current_inputs_unavailable")
