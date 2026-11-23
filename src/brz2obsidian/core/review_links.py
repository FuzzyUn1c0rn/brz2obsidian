"""Scoped normalized link evidence for review; no content parsing or I/O."""

import json
from hashlib import sha256

from brz2obsidian.content_fingerprints import canonical_equal
from brz2obsidian.content_values import content_key, content_sha, same_content
from brz2obsidian.contracts import (
    QUALIFIED_OUTPUT_FORMATS,
    LinkValidationBaseline,
    ProposalAssumption,
)

from .formats import retained_import_output
from .identity import _paths_collide, _target_context, _target_safe
from .link_meanings import (
    _query_matches_target,
    _semantic,
    resolve_link_meaning,
    resolve_occurrence,
)
from .link_validation import _validate_link_document
from .reference_targets import validate_targets


def provider_documents(facts):
    """New reviews consume owned-icon links; recorded7 replay keeps its meaning."""
    context = facts.link_context
    if (
        facts.incoming_identity.output_format not in QUALIFIED_OUTPUT_FORMATS
        or context is None
    ):
        return ()
    return context.current_documents + context.incoming_documents


def _include_occurrence_targets(documents, targets, states, inventory, ids):
    for doc in documents:
        for occurrence in doc.occurrences:
            # Discover each singleton match, even when the full query is ambiguous.
            if occurrence.query is not None and inventory == "complete":
                for target in targets:
                    if _query_matches_target(occurrence.query, target):
                        ids.add(target.target_id)
            else:
                for target in targets:
                    meaning = resolve_occurrence(
                        occurrence, (target,), states, inventory
                    )
                    if meaning.target_id is not None or meaning.candidates:
                        ids.add(target.target_id)


def _include_role_queries(roles, targets, states, inventory, ids):
    queries = roles.category_memberships.queries + tuple(
        declaration.query
        for declaration in (roles.provider, roles.owned_icon)
        if declaration.status == "valid"
    )
    for query in queries:
        for target in targets:
            meaning = resolve_link_meaning(
                query, "", None, (target,), states, inventory
            )
            if meaning.target_id is not None or meaning.candidates:
                ids.add(target.target_id)


def _include_legacy_icon(owner, state, icon_documents, targets, states, inventory, ids):
    document = icon_documents.get((owner.canonical_path, content_key(state.content)))
    if document is None:
        return
    fields = [field for field in state.structure.fields if field.key == "icon"]
    for occurrence in document.occurrences:
        if not any(
            field.span.start <= occurrence.span.start
            and occurrence.span.end <= field.span.end
            for field in fields
        ):
            continue
        for target in targets:
            meaning = resolve_occurrence(occurrence, (target,), states, inventory)
            if meaning.target_id is not None or meaning.candidates:
                ids.add(target.target_id)


def _expand_membership_and_appearance(
    states, targets, by_id, icon_documents, inventory, expanded, ids
):
    for state in states:
        if state.target_id in ids and state.structure is not None:
            ids.update(
                e.target_id for m in state.structure.memberships for e in m.entries
            )
            owner = by_id.get(state.target_id)
            roles = state.file_roles
            if roles is not None:
                if (
                    state.target_id in expanded
                    or owner is None
                    or roles.path != owner.canonical_path
                ):
                    continue
                expanded.add(state.target_id)
                _include_role_queries(roles, targets, states, inventory, ids)
                continue
            if owner is None or owner.kind != "category" or state.target_id in expanded:
                continue
            expanded.add(state.target_id)
            _include_legacy_icon(
                owner, state, icon_documents, targets, states, inventory, ids
            )


def _include_path_collisions(targets, ids):
    active_targets = tuple(t for t in targets if t.target_id in ids)
    for target in targets:
        if (
            target.canonical_path is not None
            and any(
                t.target_id in ids
                and t.canonical_path is not None
                and _paths_collide(target.canonical_path, t.canonical_path)
                for t in active_targets
            )
            and target.target_id not in ids
        ):
            ids.add(target.target_id)
            active_targets = tuple(t for t in targets if t.target_id in ids)


def consumed_context(
    documents,
    targets,
    states,
    inventory,
    *,
    include_document_targets=True,
    target_ids=(),
    appearance_documents=(),
):
    """Include query competitors, selected membership facts and path collisions."""
    ids = set(target_ids) | {
        t.target_id
        for t in targets
        if include_document_targets
        and any(t.canonical_path == d.source_path for d in documents)
    }
    _include_occurrence_targets(documents, targets, states, inventory, ids)
    by_id = {target.target_id: target for target in targets}
    icon_documents = (
        {
            (doc.source_path, content_key(doc.content)): doc
            for doc in appearance_documents + documents
        }
        if appearance_documents
        else {}
    )
    expanded = set()
    changed = True
    while changed:
        previous = set(ids)
        _expand_membership_and_appearance(
            states, targets, by_id, icon_documents, inventory, expanded, ids
        )
        _include_path_collisions(targets, ids)
        changed = ids != previous
    return (
        inventory,
        tuple(
            sorted(
                documents,
                key=lambda d: (
                    d.document_id,
                    d.source_path,
                    content_sha(d.content),
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
            and same_content(d.content, content)
        )
        portions.append(
            consumed_context(
                selected,
                targets,
                states,
                context.inventory,
                appearance_documents=provider_documents(facts),
            )
        )
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
    subject = next(
        s
        for s in facts.subjects
        if (s.item_id, s.facet) == (change.item_id, change.facet)
    )
    candidate = subject.automatic_result
    if candidate is not None and same_content(candidate.content, change.result):
        from .text_candidates import validate_text_candidate

        if validate_text_candidate(facts, change, candidate, "edited"):
            return candidate.links, candidate.link_targets, candidate.link_target_facts
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
                and same_content(document.content, change.result)
                and _validate_link_document(
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


def collection_asset_effect(facts, change):
    """Bind a first-import binary to its absent path and its exact incoming value."""
    context = facts.link_context
    if (
        facts.format_operation.kind != "collection_import"
        or context is None
        or context.inventory != "complete"
        or change.facet != "asset"
        or change.original is not None
        or change.current is not None
        or change.incoming is None
        or not same_content(change.result, change.incoming)
        or change.path != change.target_path
    ):
        return None
    current = tuple(
        t for t in context.current_targets if t.canonical_path == change.path
    )
    incoming = tuple(
        t for t in context.incoming_targets if t.canonical_path == change.path
    )
    if len(current) != 1 or current != incoming:
        return None
    (target,) = current
    if target.kind != "resource" or target.status != "safe" or target.target is None:
        return None
    old = tuple(
        row for row in context.current_target_facts if row.target_id == target.target_id
    )
    new = tuple(
        row
        for row in context.incoming_target_facts
        if row.target_id == target.target_id
    )
    if (
        len(old) == len(new) == 1
        and old[0].existence == "missing"
        and old[0].content is None
        and new[0].existence == "present"
        and same_content(new[0].content, change.incoming)
    ):
        return target, new[0]
    return None


def compatible_result_eligible(facts, change):
    return facts.link_context is not None and (
        known_result_document(facts, change) is not None
        or collection_asset_effect(facts, change) is not None
    )


def _observed_documents_bound(context, identity_inventory):
    for document in context.current_documents:
        entries = tuple(
            e for e in identity_inventory if e.current.path == document.source_path
        )
        if (
            len(entries) != 1
            or entries[0].current.existence != "present"
            or not canonical_equal(entries[0].current.content, document.content)
        ):
            return False
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
            return False
    return True


def passive_import_target(context, target):
    path = target.canonical_path
    return (
        target.kind in ("note", "resource")
        and target.identity is None
        and path is not None
        and target.target_id == f"physical:{path}"
        and target.representations == (path,)
        and any(path == candidate for candidate, _ in context.import_passive_targets)
    )


def _observed_target_bound(target, states, facts):
    entries = tuple(
        e for e in facts.identity_inventory if e.current.path == target.canonical_path
    )
    matching = tuple(s for s in states if s.target_id == target.target_id)
    if (
        not matching
        and not entries
        and passive_import_target(facts.link_context, target)
        and (
            facts.format_operation.kind == "collection_import"
            or any(subject.operation_reversal is not None for subject in facts.subjects)
        )
    ):
        return True
    if len(matching) != 1:
        return False
    (state,) = matching
    if state.existence in (
        "missing",
        "known_source_gap",
        "intentionally_uncreated",
    ):
        return not (
            state.content is not None
            or len(entries) > 1
            or any(
                e.current.existence != "absent" or e.current.content is not None
                for e in entries
            )
        )
    if len(entries) != 1:
        return False
    entry = entries[0]
    if (
        target.identity is not None and target.identity != entry.identity
    ) or not canonical_equal(state.content, entry.current.content):
        return False
    expected = (
        ("missing", "intentionally_uncreated")
        if entry.current.existence == "absent"
        else (entry.current.existence,)
    )
    return state.existence in expected


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
    if not _observed_documents_bound(context, facts.identity_inventory):
        return "current_link_context_unbound"
    _, _, targets, states = consumed_context(
        context.current_documents,
        context.current_targets,
        context.current_target_facts,
        context.inventory,
    )
    for target in targets:
        if target.kind != "tag" and not _observed_target_bound(target, states, facts):
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


def onboarding_current_context(facts):
    """Exact current observations, with no assertion about opaque link meanings."""
    context = facts.link_context
    if (
        facts.format_operation.kind not in ("onboarding", "format_transition")
        or context is None
        or current_observation_problem(facts) is not None
        or not current_lookup_coverage(facts)
    ):
        return False
    try:
        validate_targets(context.current_targets)
    except ValueError:
        return False
    for entry in facts.identity_inventory:
        if entry.current.existence != "present":
            continue
        targets = tuple(
            t for t in context.current_targets if t.canonical_path == entry.current.path
        )
        if len(targets) != 1:
            return False
        if targets[0].kind == "resource":
            continue
        documents = tuple(
            d for d in context.current_documents if d.source_path == entry.current.path
        )
        if (
            len(documents) != 1
            or not canonical_equal(documents[0].content, entry.current.content)
            or documents[0].inventory != "complete"
        ):
            return False
    return True


def _relocated_current_states(facts, candidate, owner, selected_path):
    prior = facts.link_context.current_target_facts
    if candidate.link_target_facts == prior:
        return True
    if facts.incoming_identity.output_format not in QUALIFIED_OUTPUT_FORMATS or len(
        candidate.link_target_facts
    ) != len(prior):
        return False
    for current, selected in zip(prior, candidate.link_target_facts, strict=True):
        if current.target_id != owner.target_id:
            if selected != current:
                return False
            continue
        roles, qualified = current.file_roles, selected.file_roles
        if (
            roles is None
            or qualified is None
            or qualified.path != selected_path
            or selected.content is None
            or qualified.content_sha256 != content_sha(selected.content)
            or qualified
            != roles.model_copy(
                update={
                    "path": selected_path,
                    "category": qualified.category,
                    "image_path": qualified.image_path,
                }
            )
            or selected.model_copy(update={"file_roles": roles}) != current
        ):
            return False
    return True


def _relocated_current_links_safe(
    facts, change, subject, candidate, document, observed_path
):
    context = facts.link_context
    owners = tuple(
        t for t in context.current_targets if t.canonical_path == observed_path
    )
    if len(owners) != 1:
        return False
    owner = owners[0]
    rename = change.rename_review
    if (
        rename is None
        or rename.status != "accepted"
        or rename.source_path != change.target_path
        or rename.current_path != observed_path
        or not current_lookup_coverage(facts)
        or not canonical_equal(candidate.content, change.current)
        or candidate.target != subject.source_target
        or candidate.links.document_id != document.document_id
        or candidate.links.path_mode != document.path_mode
        or candidate.links.source_path != change.target_path
        or candidate.links.inventory != context.inventory
        or not _relocated_current_states(facts, candidate, owner, change.target_path)
    ):
        return False
    prospective = owner.model_copy(
        update={
            "canonical_path": change.target_path,
            "target": subject.source_target,
            "representations": (change.target_path,),
        }
    )
    if candidate.link_targets != tuple(
        prospective if row.target_id == owner.target_id else row
        for row in context.current_targets
    ):
        return False
    return tuple(
        (o.raw, o.syntax, o.embedded, o.meaning) for o in document.occurrences
    ) == tuple(
        (o.raw, o.syntax, o.embedded, o.meaning) for o in candidate.links.occurrences
    )


def selected_current_links_safe(facts, change, *, candidate=None):
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
    observed_path = (
        change.rename_review.current_path
        if change.rename_review is not None
        else change.target_path
    )
    relocated = change.target_path != observed_path
    documents = tuple(
        d
        for d in context.current_documents
        if d.source_path == observed_path and canonical_equal(d.content, change.current)
    )
    if len(documents) != 1:
        return False
    (document,) = documents
    if relocated and candidate is None:
        return False
    if document.status != "supported" and (
        onboarding_current_context(facts)
        and change.identity_review.status == "matched"
        and not change.identity_review.repair_required
        and change.target_path == subject.current.path
    ):
        return True
    meanings = tuple(
        resolve_occurrence(
            o, context.current_targets, context.current_target_facts, context.inventory
        )
        for o in document.occurrences
    )
    valid = _validate_link_document(
        document,
        expected_content=change.current,
        expected_path=observed_path,
        targets=context.current_targets,
        target_facts=context.current_target_facts,
        inventory=context.inventory,
        baseline=current_baseline(context, document),
        affected_target_ids=()
        if facts.format_operation.kind in ("onboarding", "format_transition")
        else tuple(m.target_id for m in meanings if m.target_id is not None),
    ).valid
    if not valid or not relocated:
        return valid
    return _relocated_current_links_safe(
        facts, change, subject, candidate, document, observed_path
    )


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
        and same_content(subject.incoming, subject.baseline.content)
    )


def _present_entry_covered(facts, entry, context, reversal_physical_entry):
    records = tuple(
        t
        for t in context.current_targets
        if t.canonical_path == entry.current.path and t.kind != "tag"
    )
    if not records and reversal_physical_entry(facts, entry):
        return True
    if len(records) != 1:
        return False
    states = tuple(
        v for v in context.current_target_facts if v.target_id == records[0].target_id
    )
    if (
        len(states) != 1
        or states[0].existence != "present"
        or not canonical_equal(states[0].content, entry.current.content)
    ):
        return False
    if records[0].kind == "resource":
        if not bound_resource_record(facts, entry, records[0], states[0]):
            return False
    elif records[0].identity != entry.identity:
        return False
    return True


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
        if not _present_entry_covered(facts, entry, context, reversal_physical_entry):
            return False
    return True


def _completed_import_resource(facts, subject, target):
    if (
        subject.facet != "asset"
        or subject.baseline.content is not None
        or not retained_import_output(facts, subject)
    ):
        return False
    context = facts.link_context
    incoming = tuple(
        row for row in context.incoming_targets if row.canonical_path == subject.path
    )
    states = tuple(
        row
        for row in context.incoming_target_facts
        if row.target_id == target.target_id
    )
    return (
        incoming == (target,)
        and len(states) == 1
        and states[0].existence == "present"
        and canonical_equal(states[0].content, subject.incoming)
    )


def bound_resource_record(facts, entry, target, state):
    from .reversals import reversal_resource_record

    if reversal_resource_record(facts, entry, target, state):
        return True
    associated = any(
        entry.identity_state == "valid"
        and (
            sub.attachment is not None
            and sub.attachment.current_target_id == target.target_id
            or _completed_import_resource(facts, sub, target)
        )
        and sub.facet == entry.facet
        and entry.identity is not None
        and sub.item_id == entry.identity.item_id
        and facts.incoming_identity.collection_id == entry.identity.collection_id
        and facts.incoming_identity.module_id == entry.identity.module_id
        and sub.current.existence == entry.current.existence
        and canonical_equal(sub.current.content, entry.current.content)
        for sub in facts.subjects
    )
    origin = state.resource_origin
    retained = (
        origin is not None
        and entry.identity_state == "valid"
        and entry.identity is not None
        and origin.identity == entry.identity
        and origin.facet == entry.facet
        and origin.source_path == entry.current.path
        and state.target_id == target.target_id
        and (
            origin.identity.module_id,
            origin.identity.collection_id,
        )
        == (
            facts.incoming_identity.module_id,
            facts.incoming_identity.collection_id,
        )
    )
    context = facts.link_context
    local = (
        facts.inventory == "complete"
        and entry.identity_state == "missing"
        and entry.identity is None
        and entry.raw_identity is None
        and entry.facet is None
        and entry.current.existence == "present"
        and entry.current.content is not None
        and not entry.current.path.casefold().endswith(".md")
        and entry.target == target.target
        and state.target_id == target.target_id
        and context is not None
        and context.inventory == "complete"
        and not any(
            document.source_path == entry.current.path
            for document in context.current_documents + context.incoming_documents
        )
        and not any(
            other.target_id != target.target_id
            and other.canonical_path is not None
            and _paths_collide(other.canonical_path, entry.current.path)
            for other in context.current_targets
        )
    )
    return (
        (associated or local or retained)
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
        and canonical_equal(state.content, entry.current.content)
    )
