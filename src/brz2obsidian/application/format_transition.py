"""Separate source-stable format maintenance using the shared review lifecycle."""

from pathlib import Path
from uuid import uuid4

from brz2obsidian.contracts import SourceIdentity
from brz2obsidian.core import prepare_review

from .update_facts import record
from .update_lifecycle import (
    _baseline,
    _history,
    _observed_facts,
    _prepared,
    _read_source,
    _refused,
    _render,
    _scoped,
)


def refused(code, history=None, *, action="inspect_history"):
    return _refused(code, history, action=action).model_copy(
        update={"kind": "format_transition"}
    )


def transition_facts(history, original, incoming, *, proposal_id, generation):
    checkpoint = history.checkpoint
    retained_review = checkpoint.review
    prior = (
        retained_review.saved.plan.producer_facts
        if retained_review is not None
        else None
    )
    contextual = (
        prior is not None
        and checkpoint.manifest.boundary == "local"
        and prior.format_operation.kind in ("onboarding", "format_transition")
    )
    old_identity = (
        prior.baseline_identity if contextual else checkpoint.manifest.identity
    )
    known = not contextual or prior.format_operation.established_baseline is not None
    facts = _observed_facts(
        history,
        original,
        incoming,
        proposal_id=proposal_id,
        generation=generation,
        originals_known=known,
    )
    old_source = record(original)["source_identity"]["snapshot_digest"]
    if not known:
        current_record = next(
            subject.current.content
            for subject in facts.subjects
            if subject.item_id == "support:migration-record.json"
        )
        if current_record is None:
            raise ValueError("format_source_unavailable")
        trace = SourceIdentity.model_validate(
            record({"migration-record.json": current_record.data})["source_identity"]
        )
        if (trace.source_id, trace.module_id) != (
            old_identity.collection_id,
            old_identity.module_id,
        ):
            raise ValueError("format_source_association_changed")
        old_source = trace.snapshot_digest
    if old_source != facts.format_operation.target_source_version:
        raise ValueError("format_source_changed")
    purposes = {
        row["relative_path"]: row["purpose"]
        for row in record(incoming).get("support_artifacts", ())
    }
    roles = {
        "overview": "dashboard",
        "template": "template",
        "starter": "template",
        "configuration": "configuration",
    }
    unavailable = old_identity.output_format != 7
    subjects = tuple(
        subject.model_copy(
            update={
                "output_role": roles.get(
                    purposes.get(subject.path), subject.output_role
                ),
                **(
                    {"structure": None, "interpretation": "unsupported"}
                    if unavailable and subject.facet != "asset"
                    else {}
                ),
            }
        )
        for subject in facts.subjects
    )
    return facts.model_copy(
        update={
            "subjects": subjects,
            "baseline_identity": old_identity,
            "format_operation": facts.format_operation.model_copy(
                update={
                    "kind": "format_transition",
                    "recorded_generation": "unavailable"
                    if unavailable
                    else "supported",
                    "baseline_source_version": old_source,
                }
            ),
        }
    )


def prepare_format_transition(operations, vault, source=None):
    history = None
    try:
        history, stopped = _history(operations, vault, onboarding=True)
        if stopped is not None and stopped.code not in (
            "format_transition_required",
            "source_profile_unavailable",
            "configuration_transition_required",
        ):
            return stopped.model_copy(update={"kind": "format_transition"})
        if (
            history.status != "intact"
            or history.admission.status != "supported"
            or history.checkpoint is None
            or history.checkpoint.status != "valid"
            or not history.admission.inventory_complete
        ):
            return refused("onboarding_required", history, action="review_onboarding")
        if source is None:
            return refused(
                "format_transition_evidence_required",
                history,
                action="choose_source_reference",
            )
        retained = _read_source(operations, vault, history.checkpoint)
        original = _baseline(history.checkpoint, retained)
        directory, incoming, observed, reused = _render(operations, source, original)
        facts = transition_facts(
            history, original, incoming, proposal_id=uuid4().hex, generation=1
        )
        history = _scoped(operations, history, facts)
        review = prepare_review(facts, preflight=history.admission.preflight)
        binding = operations.observe_reviewed_source(directory, review)
        return _prepared(
            history,
            directory,
            binding,
            review,
            observed,
            reused,
            source_ref=str(Path(source).absolute()),
        )
    except ValueError as error:
        if error.args == ("format_source_changed",):
            return refused(
                "format_source_changed", history, action="choose_source_reference"
            )
        return refused("format_transition_unavailable", history)
    except OSError, TypeError, AttributeError, KeyError:
        return refused("format_transition_unavailable", history)
