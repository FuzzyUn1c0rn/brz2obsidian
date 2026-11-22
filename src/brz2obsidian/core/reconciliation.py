"""Pure exact-byte reconciliation; interpretation and all I/O belong to callers."""

import json
from dataclasses import dataclass, field, replace
from hashlib import sha256

from brz2obsidian.content_fingerprints import (
    CompletedWork,
    PendingFingerprint,
    consume_fingerprint,
    drive_inline,
    fingerprint_request,
)
from brz2obsidian.content_values import content_key, content_sha, require_inline
from brz2obsidian.contracts import (
    ChangeProvenance,
    ProposalAssumption,
    ProposedChange,
    ReconciliationFinding,
    ReconciliationInput,
    UpdateProposal,
    reconciliation_subject_id,
)
from brz2obsidian.core.identity import bind_identity

from .attachments import attachment_review
from .formats import (
    _new_source_output,
    configuration_memory_allowed,
    format_assumption,
    format_findings,
    format_proposal,
    output_semantics,
    retained_import_output,
    review_facts,
)
from .link_meanings import _OccurrenceMeanings, validate_current_link_context
from .preservation import (
    configuration_assumptions,
    preservation_decision,
    preservation_policy,
)
from .reversals import content_bytes, primary_reversal_content, reversal_safe
from .review_links import compatible_result_eligible, text_link_assumptions
from .structures import (
    structure_assumption,
    structure_dependencies,
    structure_proposal,
    validate_structure_facts,
)


def _digest(value):
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return sha256(encoded).hexdigest()


def _bytes(content):
    return content_key(content)


def _content_identity(content):
    return None if content is None else content_sha(content)


def _assumptions(facts, subject, subject_id, safety, *, reversal_fingerprint=None):
    values = (
        (
            "identity",
            (
                output_semantics(facts.baseline_identity),
                output_semantics(facts.incoming_identity),
            ),
        ),
        ("inventory", facts.inventory),
        (
            "baseline",
            (
                subject.baseline.status,
                _content_identity(subject.baseline.content),
                subject.baseline.unavailable_digest,
            ),
        ),
        (
            "current",
            (
                subject.current.existence,
                subject.current.path,
                _content_identity(subject.current.content),
            ),
        ),
        (
            "incoming",
            (subject.path, _content_identity(subject.incoming))
            + tuple(ref.model_dump(mode="json") for ref in subject.moved_navigation),
        ),
        ("interpretation", subject.interpretation),
        ("format", format_assumption(facts, subject)),
        ("structure", structure_assumption(subject.structure)),
    )
    dependencies = structure_dependencies(subject.structure, subject_id)
    assumptions = [
        ProposalAssumption(
            key=f"{subject_id}:{kind}",
            kind=kind,
            fingerprint=_digest(value),
            depends_on=tuple(a.key for a in dependencies)
            if kind == "structure"
            else (),
        )
        for kind, value in values
    ]
    assumptions.extend(
        ProposalAssumption(
            key=f"safety:{fact.key}",
            kind=fact.kind,
            fingerprint=_digest(fact.model_dump(mode="json", exclude={"subjects"})),
            depends_on=(),
        )
        for fact in safety
    )
    if subject.operation_reversal is not None:
        if reversal_fingerprint is None:
            raise ValueError("Reversal fingerprint result required")
        assumptions.append(
            ProposalAssumption(
                key=f"{subject_id}:reversal",
                kind="operation",
                fingerprint=reversal_fingerprint,
                depends_on=(f"{subject_id}:baseline", f"{subject_id}:identity"),
            )
        )
    return tuple(assumptions) + dependencies


def _findings(facts, subject, subject_id, safety):
    problems = []

    def add(code, keys):
        problems.append(
            ReconciliationFinding(
                code=code, subject_id=subject_id, blocking=True, assumption_keys=keys
            )
        )

    baseline, incoming = facts.baseline_identity, facts.incoming_identity
    identity_key = (f"{subject_id}:identity",)
    if (baseline.collection_id, baseline.module_id) != (
        incoming.collection_id,
        incoming.module_id,
    ):
        add("identity_mismatch", identity_key)
    else:
        for code in format_findings(facts):
            add(code, (f"{subject_id}:format",) if subject_id else ())
    if facts.inventory != "complete":
        add("inventory_uncertain", (f"{subject_id}:inventory",))
    if subject is not None and subject.current.existence == "unknown":
        add("current_unavailable", (f"{subject_id}:current",))
    if not {"identity", "target", "candidate", "operation"} <= {s.kind for s in safety}:
        add("missing_safety_facts", ())
    for fact in safety:
        if fact.status != "safe":
            add("unsafe_assumption", (f"safety:{fact.key}",))
    return problems


def _proposal(subject, *, automatic=False):
    original = _bytes(subject.baseline.content)
    current = _bytes(subject.current.content)
    incoming = _bytes(subject.incoming)
    if subject.baseline.status == "unknown":
        return "unresolved", None, "unknown_original", True
    if subject.incoming is None:
        return "unresolved", None, "source_absent", True
    if subject.current.existence == "absent":
        return "unresolved", None, "local_absent", True
    if incoming == original:
        disposition = "no_change" if current == original else "preserve_vault"
        return disposition, subject.current.content, "source_unchanged", False
    if automatic and subject.attachment is not None and current == original:
        return "compatible", subject.incoming, "source_only", True
    if subject.interpretation != "supported":
        return "unresolved", None, "unsupported_interpretation", True
    if current == incoming:
        return "no_change", subject.current.content, "already_current", False
    if current != original:
        return "unresolved", None, "divergent", True
    return "compatible", subject.incoming, "source_only", True


def _reversal_proposal(subject, binary_review):
    proof = subject.operation_reversal
    already_target = all(
        row.current.existence == row.target_existence
        and content_bytes(row.current.content) == content_bytes(row.target)
        for row in proof.outputs
    )
    primary = primary_reversal_content(subject)
    disposition, result, rule, requires_decision = (
        "local_deleted"
        if already_target and primary is None
        else "no_change"
        if already_target
        else "operation_reversal",
        primary if already_target else None,
        "operation_reversal",
        not already_target,
    )
    if not any(
        row.target is not None
        and content_bytes(row.target) != content_bytes(row.current.content)
        for row in proof.outputs
    ):
        binary_review = None
    return (disposition, result, rule, requires_decision), binary_review


def _comparison_safety(
    subject, binding, problems, structure_problem, outcome, structured_result
):
    disposition, result, rule, requires_decision = outcome
    if structure_problem is not None:
        structured_result = None
        disposition, result, rule, requires_decision = (
            "unresolved",
            None,
            structure_problem,
            True,
        )
    if subject.moved_navigation and not any(problem.blocking for problem in problems):
        structured_result = None
        disposition, result, rule, requires_decision = (
            "unresolved",
            None,
            "moved_navigation",
            True,
        )
    if binding.review.status != "matched":
        disposition, result, rule, requires_decision = (
            "identity_resolution",
            None,
            "identity_resolution",
            True,
        )
    if binding.review.status == "stale":
        disposition = "stale"
    if binding.rename is not None and binding.rename.status == "stale":
        structured_result = None
        disposition, result, rule, requires_decision = (
            "stale",
            None,
            "rename_review",
            True,
        )
    if any(problem.blocking for problem in problems):
        structured_result = None
        disposition, result, rule, requires_decision = (
            "refused",
            None,
            "unsafe_input",
            True,
        )
    return (disposition, result, rule, requires_decision), structured_result


def _reconcile_subject(
    facts, subject, applicability, *, reversal_fingerprint=None, _links=None
):
    changes, findings, local_changes, memory = [], [], [], []
    subject_id = reconciliation_subject_id(
        facts.incoming_identity.module_id,
        facts.incoming_identity.collection_id,
        subject.item_id,
        subject.facet,
    )
    binding = bind_identity(facts, subject, subject_id, applicability=applicability)
    subject = binding.subject
    format_review = review_facts(facts, subject)
    format_choice = format_proposal(facts, subject)
    structure_problem = (
        None
        if subject.structure is None
        else validate_structure_facts(
            subject,
            facts.baseline_identity,
            facts.incoming_identity,
            source_version=facts.format_operation.baseline_source_version,
        )
    )
    link_problem = validate_current_link_context(facts, subject, _links=_links)
    policy_allowed = (
        facts.format_operation.kind != "attachment_cleanup"
        and link_problem is None
        and (
            (format_review is None and format_choice is None)
            or configuration_memory_allowed(facts, subject)
        )
        and structure_problem is None
    )

    policy = preservation_policy(facts, subject, subject_id, policy_allowed)
    binary_review, binary_assumptions = attachment_review(
        facts, subject, subject_id, _links=_links
    )
    safety = tuple(
        sorted(
            (
                f
                for f in facts.safety_facts
                if not f.subjects or subject.item_id in f.subjects
            ),
            key=lambda f: f.key,
        )
    )
    assumptions = (
        _assumptions(
            facts,
            subject,
            subject_id,
            safety,
            reversal_fingerprint=reversal_fingerprint,
        )
        + binding.assumptions
        + (() if binding.rename is None else binding.rename.assumptions)
        + (policy.assumption,)
        + binary_assumptions
        + configuration_assumptions(facts, subject, subject_id)
        + text_link_assumptions(facts, subject, subject_id, binding.target_path)
    )
    problems = _findings(facts, subject, subject_id, safety) + list(binding.findings)
    if not reversal_safe(facts, subject, binding.target_path):
        problems.append(
            ReconciliationFinding(
                code="unsafe_assumption",
                subject_id=subject_id,
                blocking=True,
                assumption_keys=(f"{subject_id}:reversal",),
            )
        )
    if link_problem is not None:
        problems.append(
            ReconciliationFinding(
                code=link_problem,
                subject_id=subject_id,
                blocking=True,
                assumption_keys=(f"links:{subject_id}",),
            )
        )
    findings.extend(problems)
    preservation_review = policy.review
    disposition, result, rule, requires_decision = (
        (
            ("compatible", subject.incoming, "source_only", True)
            if facts.format_operation.automatic_merge
            and _new_source_output(facts, subject)
            else None
        )
        or (
            ("no_change", subject.current.content, "already_current", False)
            if retained_import_output(facts, subject)
            else None
        )
        or (policy.proposal if policy_allowed else None)
        or format_choice
        or _proposal(subject, automatic=facts.format_operation.automatic_merge)
    )
    if facts.format_operation.kind == "attachment_cleanup":
        disposition, result, rule, requires_decision = (
            ("unresolved", None, "attachment_cleanup", True)
            if subject.attachment is not None
            else (
                "preserve_vault",
                subject.current.content,
                "source_unchanged",
                False,
            )
        )
    if subject.operation_reversal is not None:
        (disposition, result, rule, requires_decision), binary_review = (
            _reversal_proposal(subject, binary_review)
        )
        preservation_review = None
    structured_result = None
    if (
        subject.structure is not None
        and subject.interpretation == "supported"
        and binding.review.status == "matched"
        and not any(problem.blocking for problem in problems)
        and rule in ("source_only", "divergent", "already_current")
    ):
        (disposition, result, rule, requires_decision), structured_result = (
            structure_proposal(
                subject,
                facts.baseline_identity,
                facts.incoming_identity,
                source_version=facts.format_operation.baseline_source_version,
                automatic=facts.format_operation.automatic_merge,
            )
        )
    (disposition, result, rule, requires_decision), structured_result = (
        _comparison_safety(
            subject,
            binding,
            problems,
            structure_problem
            if format_review is None and format_choice is None
            else None,
            (disposition, result, rule, requires_decision),
            structured_result,
        )
    )
    if (
        subject.baseline.status == "known"
        and subject.current.existence != "unknown"
        and _bytes(subject.current.content) != _bytes(subject.baseline.content)
    ):
        local_changes.append(subject_id)
    change_id = _digest(
        (
            subject_id,
            [(a.key, a.fingerprint) for a in assumptions],
            binding.target_path,
        )
    )
    decision, preservation_review, remembered, decision_findings = (
        preservation_decision(
            facts,
            subject,
            subject_id,
            change_id,
            assumptions,
            preservation_review,
            policy_allowed
            and binding.review.status == "matched"
            and not any(problem.blocking for problem in problems)
            and disposition != "stale",
        )
    )
    findings.extend(decision_findings)
    if decision is not None and not any(problem.blocking for problem in problems):
        disposition, result, rule, requires_decision = decision
        structured_result = None
    if remembered is not None:
        memory.append(remembered)
    changes.append(
        ProposedChange(
            change_id=change_id,
            subject_id=subject_id,
            item_id=subject.item_id,
            facet=subject.facet,
            path=subject.current.path,
            target_path=binding.target_path,
            original=subject.baseline.content,
            current=subject.current.content,
            incoming=subject.incoming
            if subject.operation_reversal is None
            else primary_reversal_content(subject, reverse=True),
            result=result,
            disposition=disposition,
            requires_decision=requires_decision,
            provenance=ChangeProvenance(
                producer="operation-reversal/v1"
                if rule == "operation_reversal"
                else "identity-review/v1"
                if rule in ("identity_resolution", "rename_review")
                else "structure/v1"
                if rule.startswith("structure_")
                else "preservation/v1"
                if rule
                in (
                    "source_absent",
                    "local_deleted",
                    "restoration_required",
                    "remembered_keep",
                    "remembered_decline",
                    "preservation_decision",
                )
                else "format-review/v1"
                if format_review is not None
                else "exact-bytes/v1",
                rule=rule,
            ),
            assumptions=assumptions,
            decision_dependencies=(f"identity-repair:{subject_id}",)
            if binding.review.repair_required
            else (),
            source_version=_content_identity(subject.incoming),
            format_review=format_review,
            preservation_review=preservation_review,
            attachment_review=binary_review,
            identity_review=binding.review,
            rename_review=binding.rename,
            structure_result=structured_result,
        )
    )
    change = changes[0]
    if (
        facts.format_operation.automatic_merge
        and disposition == "compatible"
        and format_review is None
        and binary_review is None
        and compatible_result_eligible(facts, change)
    ):
        change = change.model_copy(update={"requires_decision": False})
    return change, tuple(findings), tuple(local_changes), tuple(memory)


def _finish_reconciliation(facts, changes, findings, local_changes, memory):
    readiness = (
        "refused"
        if any(finding.blocking for finding in findings)
        else "review_required"
        if any(c.requires_decision for c in changes)
        else "ready"
    )
    return UpdateProposal(
        schema_id="brz2obsidian.update-proposal",
        schema_version=1,
        proposal_id=facts.proposal_id,
        generation=facts.generation,
        changes=tuple(changes),
        operation=facts.format_operation.kind,
        findings=tuple(findings),
        readiness=readiness,
        ready=readiness == "ready",
        local_changes=tuple(local_changes),
        source_version_memory=tuple(memory),
    )


@dataclass(frozen=True)
class ReconcileWork:
    facts: ReconciliationInput
    applicability: tuple = ()
    index: int = -1
    changes: tuple = ()
    findings: tuple = ()
    local_changes: tuple = ()
    memory: tuple = ()
    pending: object = None
    _links: object = field(default=None, compare=False, repr=False)


def advance_reconciliation(work, returned=None, *, context=None):
    reversal_fingerprint = None
    if work.pending is not None:
        reversal_fingerprint = consume_fingerprint(work.pending, returned)
    elif returned is not None:
        raise ValueError("Unexpected reconciliation child result")
    if work.index == -1:
        facts = ReconciliationInput.model_validate(work.facts)
        return replace(
            work,
            facts=facts,
            index=0,
            _links=_OccurrenceMeanings(facts.link_context),
            memory=facts.source_version_memory,
            findings=()
            if facts.subjects
            else tuple(_findings(facts, None, None, facts.safety_facts)),
        )
    if work.index == len(work.facts.subjects):
        return CompletedWork(
            _finish_reconciliation(
                work.facts,
                work.changes,
                work.findings,
                work.local_changes,
                work.memory,
            )
        )
    subject = work.facts.subjects[work.index]
    if subject.operation_reversal is not None and work.pending is None:
        request = fingerprint_request(
            subject.operation_reversal,
            dialect="Jc",
            scope=("reconciliation", work.facts.proposal_id, work.index, "reversal"),
            epoch=0 if context is None else context.epoch,
            context=context,
        )
        return PendingFingerprint(request, replace(work, pending=request))
    change, problems, local, remembered = _reconcile_subject(
        work.facts,
        subject,
        work.applicability,
        reversal_fingerprint=reversal_fingerprint,
        _links=work._links,
    )
    return replace(
        work,
        index=work.index + 1,
        changes=work.changes + (change,),
        findings=work.findings + problems,
        local_changes=work.local_changes + local,
        memory=work.memory + remembered,
        pending=None,
    )


def _reconcile(facts: ReconciliationInput, *, _applicability=()) -> UpdateProposal:
    return drive_inline(ReconcileWork(facts, _applicability))


def reconcile(facts: ReconciliationInput) -> UpdateProposal:
    """Prepare facts with strict current-epoch producer decision admission."""
    facts = ReconciliationInput.model_validate(facts)
    require_inline(facts)
    return _reconcile(facts)
