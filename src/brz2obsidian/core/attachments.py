"""Exact binary alternatives and bounded target allocation; never writes payloads."""

import json
from hashlib import sha256

from brz2obsidian.contracts import (
    AttachmentAlternative,
    AttachmentOutput,
    AttachmentReview,
    ProposalAssumption,
)

from .identity import _paths_collide, _target_safe
from .link_meanings import associated_link_reviews


def _hash(content):
    return None if content is None else sha256(content.data).hexdigest()


def _allocation_path(subject, ordinal):
    folder, _, name = subject.current.path.rpartition("/")
    stem, dot, _ = name.rpartition(".")
    stem = stem if dot and stem else name
    source_name = subject.path.rsplit("/", 1)[-1]
    source_stem, source_dot, suffix = source_name.rpartition(".")
    extension = "." + suffix if source_dot and source_stem else ""
    sequence = "" if ordinal == 1 else f"-{ordinal}"
    name = f"{stem} (incoming-{_hash(subject.incoming)[:8]}){sequence}{extension}"
    return f"{folder}/{name}" if folder else name


def attachment_review(facts, subject, subject_id):
    if subject.attachment is None:
        return None, ()
    if subject.operation_reversal is not None:
        return _operation_attachment_review(facts, subject, subject_id)
    association = subject.attachment.current_target_id
    prospective = []
    for other in facts.subjects:
        if (other.item_id, other.facet) == (subject.item_id, subject.facet):
            continue
        prospective.append((other.item_id, other.facet, other.path))
        if (
            other.attachment is not None
            and other.incoming is not None
            and other.current.content is not None
        ):
            for number, slot in enumerate(other.attachment.allocation_candidates, 1):
                if slot.path == _allocation_path(other, number) and _target_safe(
                    slot.path, slot.target, ()
                ):
                    prospective.append((other.item_id, other.facet, slot.path))

    def output(content, path, target_id):
        return AttachmentOutput(
            target_id=target_id,
            path=path,
            content=content,
            content_version=_hash(content),
        )

    versions = subject.current.content, subject.incoming
    alternatives = [
        AttachmentAlternative(
            choice=choice,
            outputs=()
            if content is None
            else (output(content, subject.current.path, association),),
            eligible=content is not None,
            unavailable_reasons=("content_unavailable",) if content is None else (),
        )
        for choice, content in zip(("current", "incoming"), versions, strict=True)
    ]
    both, reason, context = (), "content_unavailable", []
    if all(content is not None for content in versions):
        reason = "allocation_unavailable"
        for ordinal, candidate in enumerate(
            subject.attachment.allocation_candidates, 1
        ):
            conflicts = tuple(
                item
                for item in facts.identity_inventory
                if _paths_collide(candidate.path, item.current.path)
            )
            proposed = tuple(
                entry
                for entry in prospective
                if _paths_collide(candidate.path, entry[2])
            )
            registry_conflicts = (
                ()
                if facts.link_context is None
                else tuple(
                    (target.target_id, target.canonical_path)
                    for target in facts.link_context.current_targets
                    + facts.link_context.incoming_targets
                    if target.target_id != association
                    and target.canonical_path is not None
                    and _paths_collide(candidate.path, target.canonical_path)
                )
            )
            context.append(
                (
                    candidate.model_dump(mode="json"),
                    [
                        (
                            item.entry_id,
                            item.facet,
                            None
                            if item.identity is None
                            else item.identity.model_dump(mode="json"),
                            item.current.path,
                            _hash(item.current.content),
                            item.target.model_dump(mode="json"),
                        )
                        for item in conflicts
                    ],
                    proposed,
                    registry_conflicts,
                )
            )
            if candidate.path != _allocation_path(subject, ordinal) or not _target_safe(
                candidate.path, candidate.target, ()
            ):
                reason = "unsafe_target"
            elif conflicts or proposed or registry_conflicts:
                reason = "collision"
            elif facts.inventory != "complete":
                reason = "inventory_uncertain"
            else:
                both = (
                    output(subject.current.content, subject.current.path, association),
                    output(
                        subject.incoming,
                        candidate.path,
                        f"{association}:incoming:{_hash(subject.incoming)}",
                    ),
                )
                break
    assumption = ProposalAssumption(
        key=f"attachment:{subject_id}",
        kind="attachment",
        fingerprint=sha256(
            json.dumps(
                (
                    association,
                    _hash(subject.current.content),
                    _hash(subject.incoming),
                    subject.path,
                    facts.inventory,
                    context,
                ),
                sort_keys=True,
            ).encode()
        ).hexdigest(),
        depends_on=(
            f"{subject_id}:current",
            f"{subject_id}:incoming",
            f"{subject_id}:inventory",
            f"identity-review:{subject_id}",
        ),
    )
    alternatives.append(
        AttachmentAlternative(
            choice="both",
            outputs=both,
            eligible=bool(both),
            unavailable_reasons=() if both else (reason,),
        )
    )
    links, link_assumptions = associated_link_reviews(facts, subject, subject_id, both)
    assumptions = (assumption,) + link_assumptions
    return AttachmentReview(
        incoming_source_path=subject.path,
        alternatives=tuple(alternatives),
        assumptions=assumptions,
        links=links,
        link_inventory="unknown"
        if facts.link_context is None
        else facts.link_context.inventory,
    ), assumptions


def _operation_attachment_review(facts, subject, subject_id):
    """Offer the proved complete present outputs; omission never implies removal."""
    from .reversals import content_bytes

    proof = subject.operation_reversal
    if not any(
        row.target is not None
        and content_bytes(row.target) != content_bytes(row.current.content)
        for row in proof.outputs
    ):
        return None, ()
    alternatives = []
    for choice in ("current", "incoming"):
        present = {}
        if subject.current.content is not None:
            present[subject.current.path] = (
                subject.attachment.current_target_id,
                subject.current.content,
            )
        for row in proof.outputs:
            content = row.current.content if choice == "current" else row.target
            if content is None:
                present.pop(row.path, None)
            else:
                present[row.path] = row.target_id, content
        outputs = tuple(
            AttachmentOutput(
                target_id=target_id,
                path=path,
                content=content,
                content_version=_hash(content),
            )
            for path, (target_id, content) in sorted(
                present.items(),
                key=lambda entry: (entry[0] != subject.current.path, entry[0]),
            )
        )
        alternatives.append(
            AttachmentAlternative(
                choice=choice,
                outputs=outputs,
                eligible=bool(outputs),
                operation_bound=True,
                unavailable_reasons=() if outputs else ("content_unavailable",),
            )
        )
    assumption = ProposalAssumption(
        key=f"attachment:{subject_id}",
        kind="attachment",
        fingerprint=sha256(
            json.dumps(proof.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest(),
        depends_on=(
            f"{subject_id}:reversal",
            f"{subject_id}:current",
            f"{subject_id}:inventory",
        ),
    )
    reviews, scoped = {}, []
    for target_id in sorted(
        {subject.attachment.current_target_id} | {r.target_id for r in proof.outputs}
    ):
        view = subject.model_copy(
            update={
                "attachment": subject.attachment.model_copy(
                    update={"current_target_id": target_id}
                )
            }
        )
        links, dependencies = associated_link_reviews(facts, view, subject_id, ())
        scoped.extend(a.fingerprint for a in dependencies)
        reviews.update({(r.document_id, r.occurrence_id): r for r in links})
    link = ProposalAssumption(
        key=f"links:{subject_id}",
        kind="link",
        fingerprint=sha256(json.dumps(scoped).encode()).hexdigest(),
        depends_on=(assumption.key, f"{subject_id}:inventory"),
    )
    return AttachmentReview(
        incoming_source_path=subject.path,
        alternatives=tuple(alternatives),
        assumptions=(assumption, link),
        links=tuple(
            r.model_copy(update={"assumptions": (link,)})
            for _, r in sorted(
                reviews.items(), key=lambda entry: (entry[0][0], entry[0][1] or "")
            )
        ),
        link_inventory="unknown"
        if facts.link_context is None
        else facts.link_context.inventory,
    ), (assumption, link)
