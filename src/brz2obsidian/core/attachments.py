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
