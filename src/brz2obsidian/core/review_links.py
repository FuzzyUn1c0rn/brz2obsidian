"""Scoped normalized link evidence for review; no content parsing or I/O."""

import json
from hashlib import sha256

from brz2obsidian.contracts import LinkValidationBaseline, ProposalAssumption

from .identity import _paths_collide, _target_context, _target_safe
from .link_meanings import _semantic, resolve_occurrence
from .link_validation import validate_link_document


def consumed_context(
    documents,
    targets,
    states,
    inventory,
    *,
    include_document_targets=True,
    target_ids=(),
):
    """Include query competitors, selected membership facts and path collisions."""
    ids = set(target_ids) | {
        t.target_id
        for t in targets
        if include_document_targets
        and any(t.canonical_path == d.source_path for d in documents)
    }
    for doc in documents:
        for occurrence in doc.occurrences:
            # A single-target resolution detects lookup matches even when the full query is ambiguous.
            for target in targets:
                meaning = resolve_occurrence(occurrence, (target,), states, inventory)
                if meaning.target_id is not None or meaning.candidates:
                    ids.add(target.target_id)
    changed = True
    while changed:
        previous = set(ids)
        for state in states:
            if state.target_id in ids and state.structure is not None:
                ids.update(
                    e.target_id for m in state.structure.memberships for e in m.entries
                )
        for target in targets:
            if target.canonical_path is not None and any(
                t.target_id in ids
                and t.canonical_path is not None
                and _paths_collide(target.canonical_path, t.canonical_path)
                for t in targets
            ):
                ids.add(target.target_id)
        changed = ids != previous
    return (
        inventory,
        tuple(
            sorted(
                documents,
                key=lambda d: (
                    d.document_id,
                    d.source_path,
                    sha256(d.content.data).hexdigest(),
                ),
            )
        ),
        tuple(
            sorted(
                (t for t in targets if t.target_id in ids), key=lambda t: t.target_id
            )
        ),
        tuple(
            sorted((s for s in states if s.target_id in ids), key=lambda s: s.target_id)
        ),
    )


def text_link_assumptions(facts, subject, subject_id, target_path):
    context = facts.link_context
    if context is None or subject.attachment is not None:
        return ()
    portions = []
    for documents, targets, states, content, path in (
        (
            context.current_documents,
            context.current_targets,
            context.current_target_facts,
            subject.current.content,
            subject.current.path,
        ),
        (
            context.incoming_documents,
            context.incoming_targets,
            context.incoming_target_facts,
            subject.incoming,
            subject.path,
        ),
    ):
        selected = tuple(
            d
            for d in documents
            if d.source_path in (path, subject.current.path, target_path)
            and content is not None
            and d.content.data == content.data
        )
        portions.append(consumed_context(selected, targets, states, context.inventory))
    return (
        ProposalAssumption(
            key="text-links:" + subject_id,
            kind="link",
            fingerprint=sha256(
                json.dumps(_semantic(portions), sort_keys=True).encode()
            ).hexdigest(),
            depends_on=(
                subject_id + ":current",
                subject_id + ":incoming",
                subject_id + ":inventory",
            ),
        ),
    )


def current_baseline(context, document):
    matches = tuple(
        d
        for d in context.current_documents
        if d.document_id == document.document_id
        and d.source_path == document.source_path
    )
    if len(matches) != 1:
        return None
    return LinkValidationBaseline(
        schema_id="brz2obsidian.link-validation-baseline",
        schema_version=1,
        document=matches[0],
        targets=context.current_targets,
        target_facts=context.current_target_facts,
        inventory=context.inventory,
    )


def known_result_document(facts, change):
    """A comparison result can reuse interpretation only at its exact selected path."""
    context = facts.link_context
    if context is None or change.result is None:
        return None
    options = []
    for documents, targets, states in (
        (
            context.current_documents,
            context.current_targets,
            context.current_target_facts,
        ),
        (
            context.incoming_documents,
            context.incoming_targets,
            context.incoming_target_facts,
        ),
    ):
        for document in documents:
            if (
                document.source_path == change.target_path
                and document.content.data == change.result.data
                and validate_link_document(
                    document,
                    expected_content=change.result,
                    expected_path=change.target_path,
                    targets=targets,
                    target_facts=states,
                    inventory=context.inventory,
                    baseline=current_baseline(context, document),
                ).valid
            ):
                options.append((document, targets, states))
    return (
        options[0] if options and all(o[0] == options[0][0] for o in options) else None
    )


def compatible_result_eligible(facts, change):
    return (
        facts.link_context is not None
        and known_result_document(facts, change) is not None
    )


def current_observation_problem(facts):
    """Bind supplied current observations before lookup, baseline or deduplication."""
    context = facts.link_context
    if context is None:
        return None
    if context.inventory != "complete":
        return "current_link_context_unbound"
    if (
        len({d.document_id for d in context.current_documents})
        != len(context.current_documents)
        or len({d.source_path for d in context.current_documents})
        != len(context.current_documents)
        or len({t.target_id for t in context.current_targets})
        != len(context.current_targets)
        or len({s.target_id for s in context.current_target_facts})
        != len(context.current_target_facts)
    ):
        return "current_link_context_unbound"
    for document in context.current_documents:
        entries = tuple(
            e
            for e in facts.identity_inventory
            if e.current.path == document.source_path
        )
        if (
            len(entries) != 1
            or entries[0].current.existence != "present"
            or entries[0].current.content != document.content
        ):
            return "current_link_context_unbound"
        if any(
            resolve_occurrence(
                o,
                context.current_targets,
                context.current_target_facts,
                context.inventory,
            )
            != o.meaning
            for o in document.occurrences
        ):
            return "current_link_context_unbound"
    _, _, targets, states = consumed_context(
        context.current_documents,
        context.current_targets,
        context.current_target_facts,
        context.inventory,
    )
    for target in targets:
        if target.kind == "tag":
            continue
        entries = tuple(
            e
            for e in facts.identity_inventory
            if e.current.path == target.canonical_path
        )
        matching = tuple(s for s in states if s.target_id == target.target_id)
        if len(matching) != 1:
            return "current_link_context_unbound"
        (state,) = matching
        if state.existence in (
            "missing",
            "known_source_gap",
            "intentionally_uncreated",
        ):
            if (
                state.content is not None
                or len(entries) > 1
                or any(
                    e.current.existence != "absent" or e.current.content is not None
                    for e in entries
                )
            ):
                return "current_link_context_unbound"
            continue
        if len(entries) != 1:
            return "current_link_context_unbound"
        entry = entries[0]
        if (
            target.identity is not None and target.identity != entry.identity
        ) or state.content != entry.current.content:
            return "current_link_context_unbound"
        expected = (
            ("missing", "intentionally_uncreated")
            if entry.current.existence == "absent"
            else (entry.current.existence,)
        )
        if state.existence not in expected:
            return "current_link_context_unbound"
    return None


def rename_link_assumptions(facts, subject, subject_id, dependencies):
    """Bind inbound meaning and association without owning unrelated authored prose."""
    context = facts.link_context
    if context is None:
        return ()
    portions = []
    for documents, targets, states in (
        (
            context.current_documents,
            context.current_targets,
            context.current_target_facts,
        ),
        (
            context.incoming_documents,
            context.incoming_targets,
            context.incoming_target_facts,
        ),
    ):
        own = tuple(
            t
            for t in targets
            if t.canonical_path in (subject.current.path, subject.path)
        )
        selected = []
        meanings = []
        associations = []
        for document in documents:
            consumed = tuple(
                o
                for o in document.occurrences
                if any(
                    resolve_occurrence(
                        o, (target,), states, context.inventory
                    ).target_id
                    == target.target_id
                    for target in own
                )
            )
            if not consumed:
                continue
            selected.append(document.model_copy(update={"occurrences": consumed}))
            meanings.append(
                (
                    document.document_id,
                    document.source_path,
                    document.path_mode,
                    document.status,
                    document.issues,
                    tuple(
                        (
                            o.syntax,
                            o.embedded,
                            o.raw,
                            o.query,
                            o.meaning,
                            resolve_occurrence(o, targets, states, context.inventory),
                        )
                        for o in consumed
                    ),
                )
            )
            associations.append(
                tuple(
                    (
                        e.entry_id,
                        e.facet,
                        e.identity_state,
                        e.identity,
                        e.current.existence,
                        e.current.path,
                        e.target,
                    )
                    for e in facts.identity_inventory
                    if e.current.path == document.source_path
                )
            )
        inventory, _, lookup_targets, lookup_states = consumed_context(
            tuple(selected),
            targets,
            states,
            context.inventory,
            include_document_targets=False,
        )
        portions.append(
            (inventory, meanings, associations, lookup_targets, lookup_states)
        )
    return (
        ProposalAssumption(
            key="rename-links:" + subject_id,
            kind="link",
            fingerprint=sha256(
                json.dumps(_semantic(portions), sort_keys=True).encode()
            ).hexdigest(),
            depends_on=tuple(a.key for a in dependencies),
        ),
    )


def selected_current_links_safe(facts, change):
    context = facts.link_context
    if change.current is None:
        return True
    if context is None:
        return not current_keep_needs_proof(facts, change)
    subject = next(
        s
        for s in facts.subjects
        if (s.item_id, s.facet) == (change.item_id, change.facet)
    )
    if subject.operation_reversal is not None and subject.attachment is not None:
        return current_lookup_coverage(facts)
    if current_keep_needs_proof(facts, change) and not current_lookup_coverage(facts):
        return False
    documents = tuple(
        d
        for d in context.current_documents
        if d.source_path == change.target_path and d.content == change.current
    )
    if len(documents) != 1:
        return False
    (document,) = documents
    meanings = tuple(
        resolve_occurrence(
            o, context.current_targets, context.current_target_facts, context.inventory
        )
        for o in document.occurrences
    )
    return validate_link_document(
        document,
        expected_content=change.current,
        expected_path=change.target_path,
        targets=context.current_targets,
        target_facts=context.current_target_facts,
        inventory=context.inventory,
        baseline=current_baseline(context, document),
        affected_target_ids=tuple(
            m.target_id for m in meanings if m.target_id is not None
        ),
    ).valid


def current_keep_needs_proof(facts, change):
    subject = next(
        s
        for s in facts.subjects
        if (s.item_id, s.facet) == (change.item_id, change.facet)
    )
    return change.current is not None and not (
        subject.baseline.status == "known"
        and subject.incoming is not None
        and subject.baseline.content is not None
        and subject.incoming.data == subject.baseline.content.data
    )


def current_lookup_coverage(facts):
    from .reversals import reversal_physical_entry

    context = facts.link_context
    if context is None or context.inventory != "complete":
        return False
    for entry in facts.identity_inventory:
        if entry.current.existence == "absent":
            continue
        if entry.current.existence == "unknown":
            return False
        records = tuple(
            t
            for t in context.current_targets
            if t.canonical_path == entry.current.path and t.kind != "tag"
        )
        if not records and reversal_physical_entry(facts, entry):
            continue
        if len(records) != 1:
            return False
        states = tuple(
            v
            for v in context.current_target_facts
            if v.target_id == records[0].target_id
        )
        if (
            len(states) != 1
            or states[0].existence != "present"
            or states[0].content != entry.current.content
        ):
            return False
        if records[0].kind == "resource":
            if not bound_resource_record(facts, entry, records[0], states[0]):
                return False
        elif records[0].identity != entry.identity:
            return False
    return True


def bound_resource_record(facts, entry, target, state):
    from .reversals import reversal_resource_record

    if reversal_resource_record(facts, entry, target, state):
        return True
    associated = any(
        sub.attachment is not None
        and sub.attachment.current_target_id == target.target_id
        and entry.identity_state == "valid"
        and sub.facet == entry.facet
        and entry.identity is not None
        and sub.item_id == entry.identity.item_id
        and facts.incoming_identity.collection_id == entry.identity.collection_id
        and facts.incoming_identity.module_id == entry.identity.module_id
        and sub.current.existence == entry.current.existence
        and sub.current.content == entry.current.content
        for sub in facts.subjects
    )
    return (
        associated
        and target.kind == "resource"
        and target.identity is None
        and target.canonical_path == entry.current.path
        and target.status == "safe"
        and target.target is not None
        and _target_safe(
            target.canonical_path,
            target.target,
            _target_context(
                target.canonical_path, facts.identity_inventory, entry.entry_id
            ),
        )
        and state.existence == "present"
        and state.content == entry.current.content
    )
