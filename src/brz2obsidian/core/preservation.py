"""Pure reviewed preservation policy; no persistence, removal or restoration."""

import json
from dataclasses import dataclass
from hashlib import sha256

from brz2obsidian.contracts import (
    ConfigurationMemoryContext,
    PreservationReview,
    ProposalAssumption,
    ReconciliationFinding,
    SourceMemoryProvenance,
    SourceVersionMemory,
)
from brz2obsidian.core.formats import configuration_memory_allowed


@dataclass(frozen=True)
class PreservationPolicy:
    proposal: tuple | None
    review: PreservationReview | None
    assumption: ProposalAssumption


def _version(content):
    return None if content is None else sha256(content.data).hexdigest()


def _scope(facts, subject):
    return (
        facts.incoming_identity.module_id,
        facts.incoming_identity.collection_id,
        subject.item_id,
        subject.facet,
    )


def configuration_context(facts):
    identity = facts.incoming_identity
    return ConfigurationMemoryContext(
        profile_id=identity.profile_id,
        profile_version=identity.profile_version,
        settings_digest=identity.settings_digest,
        output_format=identity.output_format,
    )


def preservation_policy(facts, subject, subject_id, allowed):
    version = _version(subject.incoming)
    deleted = subject.current.existence == "absent"
    choice = "decline_restoration" if deleted else "keep_vault"
    records = tuple(
        record
        for record in facts.source_version_memory
        if (record.module_id, record.collection_id, record.item_id, record.facet)
        == _scope(facts, subject)
        and record.source_version == version
        and record.choice == choice
        and record.review_domain
        == ("configuration" if subject.output_role == "configuration" else "content")
        and (
            record.configuration_context == configuration_context(facts)
            if record.review_domain == "configuration"
            else record.configuration_context is None
        )
    )
    used = records if allowed and subject.current.existence != "unknown" else ()
    fingerprint = sha256(
        json.dumps(
            sorted({(record.source_version, record.choice) for record in used})
        ).encode()
    ).hexdigest()
    assumption = ProposalAssumption(
        key=f"memory:{subject_id}",
        kind="memory",
        fingerprint=fingerprint,
        depends_on=(
            f"{subject_id}:identity",
            f"{subject_id}:incoming",
            f"{subject_id}:format",
            f"{subject_id}:current",
            f"{subject_id}:structure",
        ),
    )
    review, proposal = None, None
    matches = used
    matched_ids = tuple(record.provenance.decision_id for record in matches)
    if subject.current.existence == "present" and subject.incoming is None:
        proposal = ("source_absent", subject.current.content, "source_absent", False)
        kind, choices = "source_absent", ()
    elif deleted:
        unchanged = subject.incoming is None or (
            subject.baseline.content is not None
            and subject.incoming.data == subject.baseline.content.data
        )
        suppressed = unchanged or bool(matches)
        proposal = (
            "local_deleted" if suppressed else "restoration",
            None,
            "remembered_decline"
            if matches
            else "local_deleted"
            if unchanged
            else "restoration_required",
            not suppressed,
        )
        kind, choices = (
            ("local_deleted", ())
            if suppressed
            else ("restoration", ("decline_restoration", "restore_incoming"))
        )
    elif subject.current.existence == "present" and subject.incoming is not None:
        if matches:
            proposal = (
                "preserve_vault",
                subject.current.content,
                "remembered_keep",
                False,
            )
        kind = "keep_vault"
        choices = (
            ("keep_vault",)
            if subject.current.content.data != subject.incoming.data
            and (
                subject.baseline.content is None
                or subject.baseline.content.data != subject.incoming.data
            )
            else ()
        )
        if matches:
            choices = ()
    else:
        return PreservationPolicy(None, None, assumption)
    review = PreservationReview(
        kind=kind,
        default_choice=choice,
        choices=choices if allowed and subject.output_role != "configuration" else (),
        reviewed_source_version=version,
        matched_memory_ids=matched_ids,
        provenance="source_memory" if matches else "preservation_default",
    )
    return PreservationPolicy(proposal, review, assumption)


def preservation_decision(
    facts, subject, subject_id, change_id, assumptions, review, allowed
):
    decision = next(
        (
            decision
            for decision in facts.preservation_decisions
            if (decision.item_id, decision.facet) == (subject.item_id, subject.facet)
        ),
        None,
    )
    if decision is None:
        return None, review, None, ()
    current = (
        decision.proposal_id == facts.proposal_id
        and decision.generation == facts.generation
        and (
            decision.module_id,
            decision.collection_id,
            decision.item_id,
            decision.facet,
        )
        == _scope(facts, subject)
        and decision.reviewed_source_version == _version(subject.incoming)
        and decision.reviewed_change_id == change_id
        and sorted(decision.reviewed_assumptions, key=lambda a: a.key)
        == sorted(assumptions, key=lambda a: a.key)
    )
    if (
        not current
        or not allowed
        or review is None
        or (
            decision.choice not in review.choices
            and not (
                decision.review_domain == "configuration"
                and configuration_memory_allowed(facts, subject)
                and (
                    (
                        decision.choice == "keep_vault"
                        and subject.current.existence == "present"
                    )
                    or (
                        decision.choice == "decline_restoration"
                        and subject.current.existence == "absent"
                    )
                )
                and subject.incoming is not None
            )
        )
        or decision.review_domain
        != ("configuration" if subject.output_role == "configuration" else "content")
    ):
        code = (
            "stale_preservation_decision"
            if not current
            else "unsafe_preservation_decision"
        )
        return (
            (
                "stale" if not current else "refused",
                None,
                "preservation_decision",
                True,
            ),
            review,
            None,
            (
                ReconciliationFinding(
                    code=code,
                    subject_id=subject_id,
                    blocking=current,
                    assumption_keys=tuple(a.key for a in assumptions),
                ),
            ),
        )
    record = SourceVersionMemory(
        schema_id="brz2obsidian.source-version-memory",
        schema_version=1,
        module_id=decision.module_id,
        collection_id=decision.collection_id,
        item_id=decision.item_id,
        facet=decision.facet,
        source_version=decision.reviewed_source_version,
        reviewed_incoming=subject.incoming,
        review_domain=decision.review_domain,
        configuration_context=configuration_context(facts)
        if decision.review_domain == "configuration"
        else None,
        choice=decision.choice,
        provenance=SourceMemoryProvenance(
            decision_id=decision.decision_id,
            proposal_id=decision.proposal_id,
            generation=decision.generation,
            reviewed_assumptions=decision.reviewed_assumptions,
        ),
    )
    result = subject.current.content if decision.choice == "keep_vault" else None
    proposal = (
        "preserve_vault" if result is not None else "local_deleted",
        result,
        "remembered_keep" if result is not None else "remembered_decline",
        False,
    )
    return (
        proposal,
        review.model_copy(
            update={
                "choices": (),
                "matched_memory_ids": (decision.decision_id,),
                "provenance": "explicit_user",
            }
        ),
        record,
        (),
    )


def configuration_assumptions(facts, subject, subject_id):
    if subject.output_role != "configuration":
        return ()
    context = configuration_context(facts)
    return (
        ProposalAssumption(
            key="configuration:" + subject_id,
            kind="policy",
            fingerprint=sha256(
                json.dumps(context.model_dump(mode="json"), sort_keys=True).encode()
            ).hexdigest(),
            depends_on=(f"{subject_id}:identity", f"{subject_id}:format"),
        ),
    )
