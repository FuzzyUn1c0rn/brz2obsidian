"""Exact binary alternatives and bounded target allocation; never writes payloads."""

import json
from hashlib import sha256

from brz2obsidian.contracts import (
    AttachmentAlternative, AttachmentOutput, AttachmentReview, ProposalAssumption,
)

from .identity import _paths_collide, _target_safe


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

    def output(content, path, target_id):
        return AttachmentOutput(target_id=target_id, path=path, content=content, content_version=_hash(content))

    versions = subject.current.content, subject.incoming
    alternatives = [AttachmentAlternative(
        choice=choice, outputs=() if content is None else (output(content, subject.current.path, association),),
        eligible=content is not None, unavailable_reasons=("content_unavailable",) if content is None else (),
    ) for choice, content in zip(("current", "incoming"), versions, strict=True)]
    both, reason, context = (), "content_unavailable", []
    if all(content is not None for content in versions):
        reason = "allocation_unavailable"
        for ordinal, candidate in enumerate(subject.attachment.allocation_candidates, 1):
            conflicts = tuple(item for item in facts.identity_inventory if _paths_collide(candidate.path, item.current.path))
            proposed = tuple(other.path for other in facts.subjects if (other.item_id, other.facet) != (subject.item_id, subject.facet) and _paths_collide(candidate.path, other.path))
            context.append((candidate.model_dump(mode="json"), [item.model_dump(mode="json") for item in conflicts], proposed))
            if candidate.path != _allocation_path(subject, ordinal) or not _target_safe(candidate.path, candidate.target, ()):
                reason = "unsafe_target"
            elif conflicts or proposed:
                reason = "collision"
            elif facts.inventory != "complete":
                reason = "inventory_uncertain"
            else:
                both = (output(subject.current.content, subject.current.path, association), output(subject.incoming, candidate.path, f"{association}:incoming:{_hash(subject.incoming)}"))
                break
    assumption = ProposalAssumption(
        key=f"attachment:{subject_id}", kind="attachment",
        fingerprint=sha256(json.dumps((association, _hash(subject.current.content), _hash(subject.incoming), subject.path, facts.inventory, context), sort_keys=True).encode()).hexdigest(),
        depends_on=(f"{subject_id}:current", f"{subject_id}:incoming", f"{subject_id}:inventory", f"identity-review:{subject_id}"),
    )
    alternatives.append(AttachmentAlternative(choice="both", outputs=both, eligible=bool(both), unavailable_reasons=() if both else (reason,)))
    return AttachmentReview(incoming_source_path=subject.path, alternatives=tuple(alternatives), assumptions=(assumption,)), (assumption,)
