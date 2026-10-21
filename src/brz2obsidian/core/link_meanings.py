"""Resolve source-neutral normalized queries, never Markdown or wiki syntax."""

import json
import unicodedata
from hashlib import sha256

from brz2obsidian.contracts import (
    AssociatedLinkReview,
    LinkMeaning,
    LinkQuery,
    ProposalAssumption,
)

from .identity import _paths_collide, _target_safe


def _key(value):
    return unicodedata.normalize("NFC", value).casefold()


def resolve_link_meaning(query, display, fragment, targets, target_facts, inventory):
    def result(status, target=None, state=None, matches=()):
        return LinkMeaning(
            status=status,
            target_id=None if target is None else target.target_id,
            target_identity=None if target is None else target.identity,
            path=None if target is None else target.canonical_path,
            target_version=None
            if state is None or state.content is None
            else sha256(state.content.data).hexdigest(),
            display_text=display,
            fragment=fragment,
            candidates=tuple(sorted(t.target_id for t in matches)),
        )

    if query is None:
        return result("unsupported")
    if inventory != "complete":
        return result("inventory_uncertain")
    matches = []
    for target in targets:
        if target.canonical_path is None:
            continue
        path = _key(target.canonical_path)
        paths = {path}
        if target.kind != "resource" and path.endswith(".md"):
            paths.add(path[:-3])
        aliases = {_key(name) for name in target.representations}
        value = _key(query.value)
        if (
            value in paths
            or value in aliases
            or bool(
                {_key(spelling) for spelling in query.spellings}.intersection(aliases)
            )
            or (
                query.mode == "shortened"
                and any(p.endswith("/" + value) for p in paths)
            )
        ):
            matches.append(target)
    if not matches:
        return result("missing")
    if len(matches) != 1:
        return result("ambiguous", matches=matches)
    (target,) = matches
    collisions = tuple(
        t
        for t in targets
        if t.target_id != target.target_id
        and t.canonical_path is not None
        and _paths_collide(t.canonical_path, target.canonical_path)
    )
    if (
        target.status != "safe"
        or target.target is None
        or not _target_safe(target.canonical_path, target.target, collisions)
    ):
        return result("unsafe", target)
    states = tuple(s for s in target_facts if s.target_id == target.target_id)
    if len(states) != 1:
        return result("unknown", target)
    (state,) = states
    if state.existence != "present":
        return result(state.existence, target, state)
    if state.content is None:
        return result("unknown", target, state)
    if fragment is not None:
        count = state.fragments.count(fragment)
        if state.interpretation != "supported":
            return result("unknown", target, state)
        if count != 1:
            return result(
                "fragment_missing" if count == 0 else "fragment_ambiguous",
                target,
                state,
            )
    return result("resolved", target, state)


def _semantic(value):
    if hasattr(value, "model_dump"):
        if hasattr(value, "data"):
            return {"available_sha256": sha256(value.data).hexdigest()}
        return {
            name: _semantic(getattr(value, name)) for name in type(value).model_fields
        }
    if isinstance(value, (list, tuple)):
        return [_semantic(item) for item in value]
    if isinstance(value, bytes):
        return {"bytes_sha256": sha256(value).hexdigest()}
    return value


def associated_link_reviews(facts, subject, subject_id, both_outputs):
    context = facts.link_context
    if context is None:
        return (), (
            ProposalAssumption(
                key=f"links:{subject_id}",
                kind="link",
                fingerprint=sha256(b"unknown link context").hexdigest(),
                depends_on=(f"attachment:{subject_id}", f"{subject_id}:inventory"),
            ),
        )
    association = subject.attachment.current_target_id
    documents = tuple(
        d
        for d in context.current_documents + context.incoming_documents
        if d.document_id in subject.attachment.affected_documents
        or any(
            o.meaning.target_id == association or association in o.meaning.candidates
            for o in d.occurrences
        )
    )
    relevant_ids = {association}
    relevant_ids.update(
        t.target_id
        for t in context.current_targets + context.incoming_targets
        if any(d.source_path == t.canonical_path for d in documents)
    )
    for document in documents:
        for occurrence in document.occurrences:
            relevant_ids.update(occurrence.meaning.candidates)
            if occurrence.meaning.target_id is not None:
                relevant_ids.add(occurrence.meaning.target_id)
    relevant_targets = tuple(
        t
        for t in context.current_targets + context.incoming_targets
        if t.target_id in relevant_ids
    )
    collisions = tuple(
        t
        for t in context.current_targets + context.incoming_targets
        if t.target_id not in relevant_ids
        and t.canonical_path is not None
        and any(
            r.canonical_path is not None
            and _paths_collide(t.canonical_path, r.canonical_path)
            for r in relevant_targets
        )
    )
    relevant_states = tuple(
        state
        for state in context.current_target_facts + context.incoming_target_facts
        if state.target_id in relevant_ids
    )
    fingerprint = sha256(
        json.dumps(
            _semantic(
                (
                    context.inventory,
                    documents,
                    relevant_targets,
                    collisions,
                    relevant_states,
                )
            ),
            sort_keys=True,
        ).encode()
    ).hexdigest()
    assumption = ProposalAssumption(
        key=f"links:{subject_id}",
        kind="link",
        fingerprint=fingerprint,
        depends_on=(f"attachment:{subject_id}", f"{subject_id}:inventory"),
    )
    reviews = []
    for document_id in sorted({d.document_id for d in documents}):
        old_docs = tuple(
            d for d in context.current_documents if d.document_id == document_id
        )
        new_docs = tuple(
            d for d in context.incoming_documents if d.document_id == document_id
        )
        old = (
            {}
            if len(old_docs) != 1
            else {o.occurrence_id: o.meaning for o in old_docs[0].occurrences}
        )
        new = (
            {}
            if len(new_docs) != 1
            else {o.occurrence_id: o.meaning for o in new_docs[0].occurrences}
        )
        for key in sorted(old.keys() | new.keys()):
            before, incoming = old.get(key), new.get(key)
            if not any(
                m is not None
                and (m.target_id == association or association in m.candidates)
                for m in (before, incoming)
            ):
                continue
            secondary = None
            if before is not None and len(both_outputs) == 2:
                output = both_outputs[1]
                targets = tuple(
                    t for t in context.current_targets if t.target_id == association
                )
                states = tuple(
                    state
                    for state in context.incoming_target_facts
                    if state.target_id == association
                    and state.content is not None
                    and state.content.data == output.content.data
                )
                slots = tuple(
                    slot
                    for slot in subject.attachment.allocation_candidates
                    if slot.path == output.path
                )
                secondary = before.model_copy(
                    update={
                        "status": "unknown",
                        "target_id": output.target_id,
                        "path": output.path,
                        "target_version": output.content_version,
                    }
                )
                if len(targets) == len(states) == len(slots) == 1:
                    target = targets[0].model_copy(
                        update={
                            "target_id": output.target_id,
                            "canonical_path": output.path,
                            "target": slots[0].target,
                            "representations": (output.path,),
                        }
                    )
                    state = states[0].model_copy(update={"target_id": output.target_id})
                    secondary = resolve_link_meaning(
                        LinkQuery(value=output.path, mode="exact", spellings=()),
                        before.display_text,
                        before.fragment,
                        context.current_targets + (target,),
                        context.current_target_facts + (state,),
                        context.inventory,
                    )
            choices = tuple(
                name
                for name, meaning in (
                    ("keep_current", before),
                    ("use_incoming", incoming),
                    ("use_secondary", secondary),
                )
                if meaning is not None
                and meaning.status
                in ("resolved", "known_source_gap", "intentionally_uncreated")
            )
            reviews.append(
                AssociatedLinkReview(
                    document_id=document_id,
                    occurrence_id=key,
                    old=before,
                    incoming=incoming,
                    secondary=secondary,
                    status="unchanged"
                    if before == incoming
                    else "review"
                    if choices
                    else "unsupported",
                    choices=choices,
                    assumptions=(assumption,),
                )
            )
        if not old and not new:
            reviews.append(
                AssociatedLinkReview(
                    document_id=document_id,
                    occurrence_id=None,
                    old=None,
                    incoming=None,
                    secondary=None,
                    status="unsupported",
                    choices=(),
                    assumptions=(assumption,),
                )
            )
    return tuple(reviews), (assumption,)


SAFE_LINK_STATUSES = (
    "resolved",
    "known_source_gap",
    "intentionally_uncreated",
    "external",
)


def validate_current_link_context(facts, subject):
    """Bind current observations before any remembered or explicit preservation."""
    if subject.attachment is None:
        return None
    context = facts.link_context
    if context is None or context.inventory != "complete":
        return "link_context_unavailable"
    association = subject.attachment.current_target_id

    def observed_existence(current, state):
        expected = (
            ("missing", "intentionally_uncreated")
            if current.existence == "absent"
            else (current.existence,)
        )
        return state.existence in expected

    # Complete supplied scope is checked against the independently observed inventory.
    for state in context.current_target_facts:
        records = tuple(
            t for t in context.current_targets if t.target_id == state.target_id
        )
        if len(records) != 1:
            return "link_context_invalid"
        if (
            records[0].kind != "tag"
            and state.existence == "present"
            and len(
                tuple(
                    e
                    for e in facts.identity_inventory
                    if e.current.path == records[0].canonical_path
                )
            )
            != 1
        ):
            return "link_context_invalid"
    for entry in facts.identity_inventory:
        matching = tuple(
            t for t in context.current_targets if t.canonical_path == entry.current.path
        )
        if len(matching) != 1:
            return "link_context_unavailable"
        (record,) = matching
        if record.identity is not None and record.identity != entry.identity:
            return "link_context_invalid"
        observed = tuple(
            s for s in context.current_target_facts if s.target_id == record.target_id
        )
        if (
            len(observed) != 1
            or not observed_existence(entry.current, observed[0])
            or (None if observed[0].content is None else observed[0].content.data)
            != (None if entry.current.content is None else entry.current.content.data)
        ):
            return "link_context_invalid"
        if record.kind != "resource" and entry.current.existence == "present":
            docs = tuple(
                d
                for d in context.current_documents
                if d.source_path == entry.current.path
                and d.content.data == entry.current.content.data
            )
            if len(docs) != 1:
                return "link_context_unavailable"
    targets = tuple(t for t in context.current_targets if t.target_id == association)
    states = tuple(
        s for s in context.current_target_facts if s.target_id == association
    )
    if len(targets) != 1 or len(states) != 1:
        return "link_context_invalid"
    (target,) = targets
    (state,) = states
    try:
        from .reference_targets import validate_targets

        validate_targets(targets)
    except ValueError:
        return "link_context_invalid"
    if (
        target.kind != "resource"
        or target.canonical_path != subject.current.path
        or not observed_existence(subject.current, state)
        or (None if state.content is None else state.content.data)
        != (None if subject.current.content is None else subject.current.content.data)
    ):
        return "link_context_invalid"
    from .link_validation import validate_link_target_state

    try:
        validate_link_target_state(state, context.current_targets)
    except ValueError:
        return "link_current_unsafe"
    docs = context.current_documents
    if len({d.document_id for d in docs}) != len(docs):
        return "link_context_invalid"
    if set(subject.attachment.affected_documents) - {d.document_id for d in docs}:
        return "link_context_unavailable"
    for doc in docs:
        affected = doc.document_id in subject.attachment.affected_documents or any(
            o.meaning.target_id == association or association in o.meaning.candidates
            for o in doc.occurrences
        )
        # A declared occurrence cannot omit a known affected query by falsifying its cached meaning.
        resolved = tuple(
            resolve_link_meaning(
                o.query,
                o.meaning.display_text,
                o.meaning.fragment,
                context.current_targets,
                context.current_target_facts,
                context.inventory,
            )
            if o.meaning.status != "external"
            else o.meaning
            for o in doc.occurrences
        )
        affected |= any(
            m.target_id == association or association in m.candidates for m in resolved
        )
        if not affected:
            continue
        entries = tuple(
            e for e in facts.identity_inventory if e.current.path == doc.source_path
        )
        if (
            len(entries) != 1
            or entries[0].current.content is None
            or entries[0].current.content.data != doc.content.data
        ):
            return "link_context_invalid"
        if doc.inventory != "complete" or doc.status != "supported":
            return "link_context_unavailable"
        own_targets = tuple(
            t for t in context.current_targets if t.canonical_path == doc.source_path
        )
        try:
            if len(own_targets) != 1:
                return "link_context_invalid"
            validate_targets(own_targets)
        except ValueError:
            return "link_current_unsafe"
        for occurrence, meaning in zip(doc.occurrences, resolved, strict=True):
            if occurrence.meaning != meaning:
                return "link_context_invalid"
            if (
                meaning.target_id == association or association in meaning.candidates
            ) and meaning.status not in SAFE_LINK_STATUSES:
                return "link_current_unsafe"
    return None
