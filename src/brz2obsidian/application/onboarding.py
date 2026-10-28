"""Preservation-first legacy onboarding behind the shared Operations seam."""

import tempfile
from pathlib import Path
from uuid import uuid4

from brz2obsidian.contracts import RunMetadata, SourceIdentity
from brz2obsidian.core import prepare_review, refresh_review, validate_review

from .update_contracts import UpdatePreparation
from .update_facts import output_identity, record
from .update_lifecycle import (
    _history,
    _materialize,
    _observed_facts,
    _prepared,
    _read_physical,
    _read_source,
    _refused,
    _render,
    _scope_review,
    _scoped,
    _stale_slots,
    _subjects,
)


def refused(code, history=None, *, action="inspect_history"):
    return _refused(code, history, action=action).model_copy(
        update={"kind": "onboarding"}
    )


def transition_required(facts):
    old, target = facts.baseline_identity, facts.incoming_identity
    return old.output_format != 7 or (
        old.output_format,
        old.profile_id,
        old.profile_version,
        old.settings_digest,
    ) != (
        target.output_format,
        target.profile_id,
        target.profile_version,
        target.settings_digest,
    )


def route_onboarding(result):
    prepared = result.preparation
    if prepared is None or not transition_required(prepared.review.facts):
        return result
    return result.model_copy(
        update={
            "ready": False,
            "next_actions": tuple(
                dict.fromkeys((*result.next_actions, "review_format_transition"))
            ),
            "findings": tuple(
                dict.fromkeys((*result.findings, "recorded_format_transition_required"))
            ),
        }
    )


def _recorded_identity(history, incoming_identity, proposal_id=None):
    checkpoint = history.checkpoint
    if (
        history.status == "intact"
        and checkpoint is not None
        and checkpoint.review is not None
    ):
        facts = checkpoint.review.saved.plan.producer_facts
        if (
            facts.format_operation.kind == "onboarding"
            and facts.proposal_id == proposal_id
        ):
            return facts.baseline_identity
    rows = tuple(
        r for r in history.admission.inventory if r.path == "migration-record.json"
    )
    try:
        old = (
            output_identity(record(_read_physical(history.admission.vault, rows)))
            if rows
            else incoming_identity
        )
    except OSError, ValueError, KeyError, TypeError:
        return incoming_identity
    if (old.collection_id, old.module_id) != (
        incoming_identity.collection_id,
        incoming_identity.module_id,
    ):
        raise ValueError("association_mismatch")
    return old


def _facts(history, original, incoming, *, proposal_id, generation):
    facts = _observed_facts(
        history,
        original or incoming,
        incoming,
        proposal_id=proposal_id,
        generation=generation,
        originals_known=original is not None,
        onboarding=True,
    )
    old = _recorded_identity(history, facts.incoming_identity, proposal_id)
    if old != facts.baseline_identity:
        facts = facts.model_copy(update={"baseline_identity": old})
    if original is None and transition_required(facts):
        facts = facts.model_copy(
            update={
                "format_operation": facts.format_operation.model_copy(
                    update={"recorded_generation": "unavailable"}
                ),
                "subjects": tuple(
                    s.model_copy(update={"interpretation": "unsupported"})
                    if s.facet != "asset"
                    else s
                    for s in facts.subjects
                ),
            }
        )
    return facts


def _original_payload(operations, history, source):
    """Reproduce supported historical bytes from an independently bound archive."""
    if source is None:
        return None
    try:
        rows = tuple(
            r for r in history.admission.inventory if r.path == "migration-record.json"
        )
        if len(rows) != 1:
            return None
        old = record(_read_physical(history.admission.vault, rows))
        identity = SourceIdentity.model_validate(old["source_identity"])
        metadata = RunMetadata.model_validate(old["run_metadata"])
        policy = operations._configured_workflow().binding.policy
        if (
            old["schema_version"] != 7
            or metadata.renderer_version != "7"
            or (
                identity.module_id,
                identity.module_version,
                old["profile_id"],
                old["profile_version"],
            )
            != (
                policy.module_id,
                policy.module_version,
                policy.profile_id,
                policy.profile_version,
            )
            or old.get("settings") not in (None, {})
        ):
            return None
        with tempfile.TemporaryDirectory(
            prefix="brz2obsidian-onboarding-original-"
        ) as owned:
            _, payload, observed, _ = _render(
                operations,
                source,
                {},
                metadata=metadata,
                directory=Path(owned) / "incoming",
            )
        if observed != identity or record(payload) != old:
            return None
        return payload
    except OSError, ValueError, KeyError, TypeError, AttributeError:
        return None


def _retained_original_payload(history, proposal_id, incoming):
    checkpoint = history.checkpoint
    if history.status != "intact" or checkpoint is None or checkpoint.review is None:
        return None
    facts = checkpoint.review.saved.plan.producer_facts
    operation = facts.format_operation
    if (
        facts.proposal_id != proposal_id
        or operation.kind != "onboarding"
        or operation.recorded_generation != "supported"
        or operation.established_baseline is None
        or operation.baseline_source_version != operation.target_source_version
        or output_identity(record(incoming)) != facts.baseline_identity
        or record(incoming)["source_identity"]["snapshot_digest"]
        != operation.baseline_source_version
        or any(
            s.baseline.content is None
            or incoming.get(s.path) != s.baseline.content.data
            for s in facts.subjects
        )
    ):
        return None
    return incoming


def prepare_onboarding(operations, vault, source=None, *, original_source=None):
    history, stopped = _history(operations, vault)
    if stopped is not None and stopped.status == "recovery_required":
        return stopped.model_copy(update={"kind": "onboarding"})
    if (
        history.admission.status == "supported"
        and history.admission.repository.kind == "none"
        and "review_initialization" in history.admission.admitted_actions
    ):
        return refused("initialization_required", history).model_copy(
            update={
                "next_actions": ("initialize_vault",),
                "vault": history.admission.vault,
            }
        )
    if history.status == "intact":
        return refused("existing_history_requires_update", history)
    if source is None:
        return refused(
            "onboarding_evidence_required", history, action="choose_source_reference"
        )
    try:
        if (
            history.admission.status != "supported"
            or not history.admission.inventory_complete
        ):
            raise ValueError("current_admission_required")
        historical_source = original_source if original_source is not None else source
        original = _original_payload(operations, history, historical_source)
        directory, incoming, observed, reused = _render(
            operations, source, original or {}
        )
        if (
            original is not None
            and record(original)["source_identity"]["snapshot_digest"]
            != observed.snapshot_digest
        ):
            return refused(
                "source_changes_require_separate_update", history
            ).model_copy(
                update={
                    "next_actions": ("choose_matching_onboarding_source",),
                }
            )
        facts = _facts(
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
            original_source_ref=str(Path(historical_source).absolute())
            if original is not None
            else None,
        )
    except OSError, ValueError, KeyError, TypeError, AttributeError:
        return refused("onboarding_unavailable", history)


def reobserve_onboarding(operations, preparation):
    history = operations.inspect_history(preparation.vault)
    try:
        if history.admission.status == "recovery_first":
            return (
                None,
                _history(operations, preparation.vault)[1].model_copy(
                    update={"kind": "onboarding"}
                ),
                None,
            )
        if (
            history.admission.status != "supported"
            or not history.admission.inventory_complete
        ):
            raise ValueError("current_admission_required")
        locator = history.checkpoint.locator if history.checkpoint is not None else None
        if locator != preparation.locator or history.status not in ("absent", "intact"):
            raise ValueError("association_or_history_changed")
        if history.status == "intact" and (
            history.checkpoint.review is None
            or history.checkpoint.manifest.boundary not in ("local", "prepared")
            or history.checkpoint.review.saved.plan.facts.format_operation.kind
            != "onboarding"
            or history.checkpoint.review.saved.plan.facts.proposal_id
            != preparation.review.proposal.proposal_id
        ):
            raise ValueError("current_onboarding_history_required")
        directory = Path(preparation.payload_directory).absolute()
        if (
            directory.name != "incoming"
            or directory.parent.parent != Path(tempfile.gettempdir())
            or not directory.parent.name.startswith("brz2obsidian-update-")
        ):
            raise ValueError("owned_payload_required")
        if validate_review(preparation.review).status != "accepted":
            raise ValueError("invalid_review")
        actual = operations.observe_reviewed_source(directory, preparation.review)
        if actual != preparation.source_binding:
            raise ValueError("source_payload_changed")
        incoming = _read_physical(directory, actual.files)
        original = _retained_original_payload(
            history, preparation.review.proposal.proposal_id, incoming
        )
        if original is None and preparation.source_ref is not None:
            original = _original_payload(
                operations,
                history,
                preparation.original_source_ref or preparation.source_ref,
            )
        if preparation.source_ref is not None:
            metadata = RunMetadata.model_validate(record(incoming)["run_metadata"])
            with tempfile.TemporaryDirectory(
                prefix="brz2obsidian-onboarding-check-"
            ) as owned:
                fresh, _, observed_source, _ = _render(
                    operations,
                    preparation.source_ref,
                    original or {},
                    metadata=metadata,
                    directory=Path(owned) / "incoming",
                )
                fresh_binding = operations.observe_reviewed_source(
                    fresh, preparation.review
                )
            if (
                observed_source != preparation.observed_source
                or fresh_binding.files != actual.files
            ):
                raise ValueError("incoming_source_changed")
        else:
            saved_binding = (
                history.checkpoint.manifest.reviewed_source
                if history.checkpoint
                else None
            )
            if (
                saved_binding is None
                or saved_binding.proposal_id != actual.proposal_id
                or saved_binding.incoming_identity != actual.incoming_identity
                or saved_binding.target_source_version != actual.target_source_version
                or saved_binding.files != actual.files
                or history.checkpoint.manifest.observed_source
                != preparation.observed_source
            ):
                raise ValueError("persisted_source_authority_required")
        facts = _facts(
            history,
            original,
            incoming,
            proposal_id=preparation.review.proposal.proposal_id,
            generation=preparation.review.proposal.generation,
        )
        history = _scope_review(operations, history, facts, preparation.review)
        review = preparation.review
        changed = (
            facts != review.facts or history.admission.preflight != review.preflight
        )
        if changed:
            facts = facts.model_copy(update={"generation": facts.generation + 1})
            transition = refresh_review(
                review, facts, preflight=history.admission.preflight
            )
            if transition.status != "accepted":
                raise ValueError("current_review_unavailable")
            review = transition.plan
            actual = operations.observe_reviewed_source(directory, review)
        result = _prepared(
            history,
            directory,
            actual,
            review,
            preparation.observed_source,
            source_ref=preparation.source_ref,
            original_source_ref=preparation.original_source_ref,
            status="stale_review" if changed else "prepared_review",
            code="current_facts_changed" if changed else "current",
            stale=_stale_slots(preparation.review, review) if changed else 0,
        )
        return history, result, incoming
    except OSError, ValueError, KeyError, TypeError, AttributeError:
        return None, refused("current_onboarding_unavailable", history), None


def save_onboarding(operations, history, current, *, progress=None):
    prepared = current.preparation
    association = prepared.locator.association if prepared.locator else None
    captured = operations.capture_checkpoint(
        prepared.vault,
        prepared.payload_directory,
        vault_id=association.vault_id
        if association
        else "vault-" + prepared.review.proposal.proposal_id,
        import_id=association.import_id
        if association
        else "import-" + prepared.review.proposal.proposal_id,
        identity=prepared.review.facts.baseline_identity,
        admission=history.admission,
        subjects=_subjects(prepared.review.producer_facts, prepared.review)
        if history.admission.preflight.consents
        else (),
        review=prepared.review,
        source_binding=prepared.source_binding,
        observed_source=prepared.observed_source,
        **({"progress": progress} if progress is not None else {}),
    )
    if captured.status not in ("captured", "unchanged") or captured.locator is None:
        return refused(captured.code, history).model_copy(
            update={
                "capture": captured,
                "history_retained": captured.history_retained,
                "checkpoint_commit": captured.commit,
            }
        )
    return current.model_copy(
        update={
            "code": "saved",
            "capture": captured,
            "history_retained": True,
            "checkpoint_commit": captured.commit,
            "checkpoint": captured.locator,
            "preparation": prepared.model_copy(update={"locator": captured.locator}),
        }
    )


def resume_onboarding(operations, history, observed):
    checkpoint = history.checkpoint
    plan = checkpoint.review.saved.plan
    incoming = _read_source(operations, history.admission.vault, checkpoint, observed)
    binding = checkpoint.manifest.reviewed_source
    directory = _materialize(incoming, {r.path: r.mode for r in binding.files})
    fresh_binding = operations.observe_reviewed_source(directory, plan)
    prepared = UpdatePreparation(
        schema_id="brz2obsidian.update-preparation",
        schema_version=1,
        kind="onboarding",
        vault=history.admission.vault,
        locator=checkpoint.locator,
        payload_directory=str(directory),
        source_binding=fresh_binding,
        observed_source=checkpoint.manifest.observed_source,
        retained_source_provenance=False,
        review=plan,
    )
    return reobserve_onboarding(operations, prepared)[1]
