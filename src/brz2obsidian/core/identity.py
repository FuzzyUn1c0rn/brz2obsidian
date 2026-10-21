"""Bind imported items to immutable inventory and explicit review facts without I/O."""

import json
import unicodedata
from dataclasses import dataclass
from hashlib import sha256

from brz2obsidian.contracts import (
    IdentityCandidate,
    IdentityReview,
    ProposalAssumption,
    ReconciliationFinding,
    ReconciliationSubject,
    RenameReview,
)


@dataclass(frozen=True)
class IdentityBinding:
    subject: ReconciliationSubject
    review: IdentityReview
    rename: RenameReview | None
    target_path: str
    findings: tuple[ReconciliationFinding, ...]
    assumptions: tuple[ProposalAssumption, ...]


def _digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def _same_owner(facts, subject, item):
    claim = item.identity
    return claim is not None and (
        claim.module_id,
        claim.collection_id,
        claim.item_id,
    ) == (
        facts.incoming_identity.module_id,
        facts.incoming_identity.collection_id,
        subject.item_id,
    )


def _same_identity(facts, subject, item):
    return _same_owner(facts, subject, item) and item.facet == subject.facet


def _claim_fact(item):
    return (
        item.entry_id,
        item.facet,
        item.identity_state,
        None if item.identity is None else item.identity.model_dump(),
    )


def _entry_fact(item):
    content = item.current.content
    return {
        "claim": _claim_fact(item),
        "raw_identity": item.raw_identity,
        "title": item.title,
        "current": (
            item.current.existence,
            item.current.path,
            None if content is None else sha256(content.data).hexdigest(),
        ),
        "target": item.target.model_dump(),
    }


def _normalized(path):
    return unicodedata.normalize("NFC", unicodedata.normalize("NFC", path).casefold())


def _paths_collide(left, right):
    left, right = _normalized(left), _normalized(right)
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def _target_context(path, items, selected_id):
    return tuple(
        item
        for item in items
        if item.entry_id != selected_id
        and item.current.existence != "absent"
        and _paths_collide(item.current.path, path)
    )


def _target_safe(path, target, collisions):
    reserved = {"con", "prn", "aux", "nul"} | {
        f"{prefix}{number}" for prefix in ("com", "lpt") for number in range(1, 10)
    }
    return (
        target.status == "safe"
        and target.containment == "contained"
        and target.normalized_path == _normalized(path)
        and not collisions
        and all(
            part not in ("", ".", "..")
            and not part.endswith((".", " "))
            and part.split(".", 1)[0].casefold() not in reserved
            and not any(ord(char) < 32 or char in '<>:"\\|?*' for char in part)
            for part in path.split("/")
        )
    )


def _assumptions_equal(left, right):
    return sorted(left, key=lambda value: value.key) == sorted(
        right, key=lambda value: value.key
    )


def _decision_current(decision, facts, subject, assumptions):
    return (
        decision.proposal_id == facts.proposal_id
        and decision.generation == facts.generation
        and decision.collection_id == facts.incoming_identity.collection_id
        and decision.module_id == facts.incoming_identity.module_id
        and decision.item_id == subject.item_id
        and decision.facet == subject.facet
        and _assumptions_equal(decision.reviewed_assumptions, assumptions)
    )


def _rename(facts, subject, subject_id, selected, items, identity_review, assumptions):
    decision = next(
        (d for d in facts.rename_decisions if (d.item_id, d.facet) == (subject.item_id, subject.facet)), None
    )
    current_path = subject.current.path
    if selected is None or subject.path == current_path:
        findings = ()
        if decision is not None:
            findings = (
                ReconciliationFinding(
                    code="unsafe_rename_decision",
                    subject_id=subject_id,
                    blocking=True,
                    assumption_keys=tuple(a.key for a in assumptions),
                ),
            )
        return None, current_path, findings
    collisions = _target_context(subject.path, items, selected.entry_id)
    planned = tuple(
        sorted(
            (other.item_id, other.facet, other.path, other.source_target.model_dump())
            for other in facts.subjects
            if (other.item_id, other.facet) != (subject.item_id, subject.facet)
            and _paths_collide(other.path, subject.path)
            and any(
                (d.item_id, d.facet) == (other.item_id, other.facet) and d.choice == "source_path"
                for d in facts.rename_decisions
            )
        )
    )
    safe = (
        identity_review.status == "matched"
        and not identity_review.repair_required
        and _target_safe(subject.path, subject.source_target, collisions)
        and not planned
    )
    assumption = ProposalAssumption(
        key=f"rename:{subject_id}",
        kind="target",
        fingerprint=_digest(
            (
                current_path,
                subject.path,
                subject.source_target.model_dump(),
                [_entry_fact(item) for item in collisions],
                planned,
                [(a.key, a.fingerprint) for a in assumptions],
            )
        ),
        depends_on=tuple(a.key for a in assumptions)
        + tuple(
            f"rename:{_digest((facts.incoming_identity.module_id, facts.incoming_identity.collection_id, other.item_id, other.facet))}"
            for other in facts.subjects
            if any((item_id, facet) == (other.item_id, other.facet) for item_id, facet, _, _ in planned)
        ),
    )
    status, required, decision_id, provenance = (
        "offered" if safe else "blocked",
        False,
        None,
        "unresolved",
    )
    target_path, findings = current_path, []
    if decision is not None:
        decision_id, provenance = decision.decision_id, "explicit_user"
        if not _decision_current(decision, facts, subject, (assumption,)):
            status, required = "stale", True
            findings.append(
                ReconciliationFinding(
                    code="stale_rename_decision",
                    subject_id=subject_id,
                    blocking=False,
                    assumption_keys=(assumption.key,),
                )
            )
        elif decision.choice == "keep_path":
            status = "declined"
        elif not safe:
            status, required = "blocked", True
            findings.append(
                ReconciliationFinding(
                    code="unsafe_rename_target",
                    subject_id=subject_id,
                    blocking=True,
                    assumption_keys=(assumption.key,),
                )
            )
        else:
            status, target_path = "accepted", subject.path
    return (
        RenameReview(
            current_path=current_path,
            source_path=subject.path,
            status=status,
            requires_decision=required,
            decision_id=decision_id,
            provenance=provenance,
            assumptions=(assumption,),
        ),
        target_path,
        tuple(findings),
    )


def bind_identity(facts, subject, subject_id):
    items = tuple(sorted(facts.identity_inventory, key=lambda item: item.entry_id))
    by_id = {item.entry_id: item for item in items}
    matches = tuple(item for item in items if _same_identity(facts, subject, item))
    selected = (
        matches[0]
        if len(matches) == 1 and matches[0].identity_state == "valid"
        else None
    )
    safety = tuple(
        sorted(
            (
                fact
                for fact in facts.safety_facts
                if not fact.subjects or subject.item_id in fact.subjects
            ),
            key=lambda fact: fact.key,
        )
    )
    dependencies = (
        f"{subject_id}:identity",
        f"{subject_id}:inventory",
        *(f"safety:{fact.key}" for fact in safety),
    )
    query = ProposalAssumption(
        key=f"identity-review:{subject_id}",
        kind="identity",
        fingerprint=_digest(
            (
                facts.incoming_identity.module_id,
                facts.incoming_identity.collection_id,
                subject.item_id,
                subject.facet,
                facts.inventory,
                [_claim_fact(item) for item in matches],
                [fact.model_dump(mode="json") for fact in safety],
            )
        ),
        depends_on=dependencies,
    )
    candidates = []
    for item in items:
        same = _same_identity(facts, subject, item)
        same_title = subject.title is not None and item.title == subject.title
        same_path = item.current.path == subject.path
        if not (
            same
            or (
                selected is None
                and (item.identity_state != "valid" or same_title or same_path)
            )
        ):
            continue
        collisions = _target_context(item.current.path, items, item.entry_id)
        assumption = ProposalAssumption(
            key=f"identity-candidate:{subject_id}:{item.entry_id}",
            kind="identity",
            fingerprint=_digest(
                (_entry_fact(item), [_entry_fact(other) for other in collisions])
            ),
            depends_on=(query.key, *dependencies),
        )
        candidates.append(
            IdentityCandidate(
                entry_id=item.entry_id,
                facet=item.facet,
                current=item.current,
                title=item.title,
                identity_state=item.identity_state,
                identity=item.identity,
                suggestion="identity"
                if same
                else "title"
                if same_title
                else "path"
                if same_path
                else "unassociated",
                eligible=same
                or (item.facet in (None, subject.facet) and (
                    (item.identity_state != "valid" and item.identity is None)
                    or (item.facet is None and _same_owner(facts, subject, item))
                )),
                target_safe=_target_safe(item.current.path, item.target, collisions),
                assumptions=(assumption,),
            )
        )
    candidate_by_id = {candidate.entry_id: candidate for candidate in candidates}
    status = "matched" if selected is not None else "unresolved"
    reason = (
        "unique_identity"
        if selected is not None
        else "duplicate_identity"
        if len(matches) > 1
        else "identity_unavailable"
    )
    decision_id, disassociate, provenance = (
        None,
        (),
        "unique_identity" if selected else "unresolved",
    )
    findings = []

    def finding(code, blocking, keys=None):
        findings.append(
            ReconciliationFinding(
                code=code,
                subject_id=subject_id,
                blocking=blocking,
                assumption_keys=(query.key,) if keys is None else keys,
            )
        )

    decision = next(
        (d for d in facts.association_decisions if (d.item_id, d.facet) == (subject.item_id, subject.facet)), None
    )
    if decision is not None:
        decision_id, provenance = decision.decision_id, "explicit_user"
        requested = (decision.selected_entry_id, *decision.disassociate_entry_ids)
        reviewed = (query,) + tuple(
            a
            for candidate in candidates
            if candidate.entry_id in requested
            for a in candidate.assumptions
        )
        candidate = candidate_by_id.get(decision.selected_entry_id)
        if not _decision_current(decision, facts, subject, reviewed):
            selected, status, reason = None, "stale", "decision_stale"
            finding("stale_identity_decision", False)
        elif (
            facts.inventory != "complete"
            or candidate is None
            or not candidate.eligible
            or any(
                entry not in by_id or not _same_identity(facts, subject, by_id[entry])
                for entry in decision.disassociate_entry_ids
            )
        ):
            selected, status, reason = None, "refused", "decision_unsafe"
            finding("unsafe_identity_decision", True)
        else:
            selected = by_id[decision.selected_entry_id]
            disassociate = decision.disassociate_entry_ids
            expected_clears = {
                item.entry_id for item in matches if item.entry_id != selected.entry_id
            }
            if set(disassociate) != expected_clears:
                status, reason = "association_proposed", "repair_incomplete"
                finding("identity_repair_incomplete", False)
            else:
                status, reason = "association_proposed", "association_proposed"
    effective = (
        subject
        if selected is None
        else subject.model_copy(update={"current": selected.current})
    )
    if selected is not None:
        candidate = candidate_by_id[selected.entry_id]
        affected = (candidate,) + tuple(
            candidate_by_id[entry] for entry in disassociate
        )
        unsafe = tuple(
            a.key
            for affected_candidate in affected
            if not affected_candidate.target_safe
            for a in affected_candidate.assumptions
        )
        if unsafe:
            status, reason = "refused", "target_unsafe"
            finding("unsafe_identity_target", True, unsafe)
        elif decision is None and (
            subject.current.existence,
            None if subject.current.content is None else subject.current.content.data,
        ) != (
            selected.current.existence,
            None if selected.current.content is None else selected.current.content.data,
        ):
            status, reason = "refused", "current_mismatch"
            finding("current_inventory_mismatch", True)
    repair_required = (
        selected is None or selected.identity_state != "valid" or selected.facet != subject.facet or len(matches) != 1
    )
    if (
        selected is not None
        and not repair_required
        and status == "association_proposed"
    ):
        status, reason = "matched", "unique_identity"
    review = IdentityReview(
        status=status,
        reason=reason,
        selected_entry_id=None if selected is None else selected.entry_id,
        candidates=tuple(candidates),
        repair_required=repair_required,
        disassociate_entry_ids=disassociate,
        decision_id=decision_id,
        provenance=provenance,
        assumptions=(query,),
    )
    used = (
        set(candidate_by_id) if selected is None else {selected.entry_id, *disassociate}
    )
    assumptions = (query,) + tuple(
        a
        for candidate in candidates
        if candidate.entry_id in used
        for a in candidate.assumptions
    )
    rename, target_path, rename_findings = _rename(
        facts, effective, subject_id, selected, items, review, assumptions
    )
    return IdentityBinding(
        effective,
        review,
        rename,
        target_path,
        tuple(findings) + rename_findings,
        assumptions,
    )
