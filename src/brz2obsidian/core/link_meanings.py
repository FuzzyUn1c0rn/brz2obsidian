"""Resolve source-neutral normalized queries, never Markdown or wiki syntax."""

import json
import unicodedata
from hashlib import sha256

from brz2obsidian.content_values import content_key, content_sha, same_content
from brz2obsidian.contracts import (
    AssociatedLinkReview,
    InlineExactContent,
    LinkMeaning,
    LinkQuery,
    OpaqueContent,
    ProposalAssumption,
    ReferenceTarget,
)

from .identity import _paths_collide, _target_safe


def _key(value):
    return unicodedata.normalize("NFC", value).casefold()


def same_canonical_path(left, right):
    return _key(left) == _key(right)


def _path_spellings(path, *, note):
    normalized = _key(path)
    if note and normalized.endswith(".md"):
        return normalized, normalized[:-3]
    return (normalized,)


def matches_exact_note_path(query, path):
    """Match a canonical note path, without short names or alias resolution."""
    return query.mode == "exact" and _key(query.value) in _path_spellings(
        path, note=True
    )


def _query_matches_target(query, target):
    if target.canonical_path is None:
        return False
    paths = _path_spellings(target.canonical_path, note=target.kind != "resource")
    aliases = {_key(name) for name in target.representations}
    value = _key(query.value)
    return (
        value in paths
        or value in aliases
        or bool({_key(spelling) for spelling in query.spellings}.intersection(aliases))
        or (query.mode == "shortened" and any(p.endswith("/" + value) for p in paths))
    )


def _present_link_status(state, fragment):
    if state.existence != "present":
        return state.existence
    if state.content is None:
        return "unknown"
    if fragment is not None:
        count = state.fragments.count(fragment)
        if state.interpretation != "supported":
            return "unknown"
        if count != 1:
            return "fragment_missing" if count == 0 else "fragment_ambiguous"
    return "resolved"


def resolve_link_meaning(query, display, fragment, targets, target_facts, inventory):
    def result(status, target=None, state=None, matches=()):
        return LinkMeaning(
            status=status,
            target_id=None if target is None else target.target_id,
            target_identity=None if target is None else target.identity,
            path=None if target is None else target.canonical_path,
            target_version=None
            if state is None or state.content is None
            else content_sha(state.content),
            display_text=display,
            fragment=fragment,
            candidates=tuple(sorted(t.target_id for t in matches)),
        )

    if query is None:
        return result("unsupported")
    if inventory != "complete":
        return result("inventory_uncertain")
    matches = [target for target in targets if _query_matches_target(query, target)]
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
    return result(_present_link_status(state, fragment), target, state)


def resolve_occurrence(occurrence, targets, target_facts, inventory):
    """Only a query-free external fact can bypass internal target resolution."""
    if occurrence.query is None and occurrence.meaning.status == "external":
        return occurrence.meaning
    return resolve_link_meaning(
        occurrence.query,
        occurrence.meaning.display_text,
        occurrence.meaning.fragment,
        targets,
        target_facts,
        inventory,
    )


class _OccurrenceMeanings:
    """Recomputed meanings retained only for one immutable reconciliation input."""

    def __init__(self, context):
        self.context = context
        self._inputs = (
            {}
            if context is None
            else {
                stage: (
                    getattr(context, stage + "_targets"),
                    getattr(context, stage + "_target_facts"),
                    context.inventory,
                )
                for stage in ("current", "incoming")
            }
        )
        self._meanings = {}
        self._current_scope = None

    def current_scope(self, context, inventory):
        inputs = (
            context,
            context.current_targets,
            context.current_target_facts,
            context.current_documents,
            inventory,
        )
        if context is not self.context:
            return _CurrentScope(*inputs)
        if self._current_scope is None:
            self._current_scope = _CurrentScope(*inputs)
        if all(a is b for a, b in zip(self._current_scope.inputs, inputs, strict=True)):
            return self._current_scope
        return _CurrentScope(*inputs)

    def resolve(self, context, stage, occurrence):
        targets = getattr(context, stage + "_targets")
        states = getattr(context, stage + "_target_facts")
        inventory = context.inventory
        bound = self._inputs.get(stage)
        if (
            context is not self.context
            or bound is None
            or targets is not bound[0]
            or states is not bound[1]
            or inventory != bound[2]
            or occurrence.query is None
            and occurrence.meaning.status == "external"
        ):
            return resolve_occurrence(occurrence, targets, states, inventory)
        query = occurrence.query
        key = (
            stage,
            id(occurrence),
            None if query is None else (query.value, query.mode, query.spellings),
            occurrence.meaning.display_text,
            occurrence.meaning.fragment,
        )
        if key not in self._meanings:
            meaning = resolve_occurrence(occurrence, targets, states, inventory)
            # Hold occurrences and query objects, not only their reusable ids.
            # An exception above leaves no entry and cannot suppress validation.
            self._meanings[key] = occurrence, query, meaning
        return self._meanings[key][2]


def _buckets(items, key):
    result = {}
    for item in items:
        result.setdefault(key(item), []).append(item)
    return {key: tuple(values) for key, values in result.items()}


class _CurrentScope:
    """Ordered exact-key lookup references for one observed current scope."""

    def __init__(self, context, targets, states, documents, inventory):
        self.inputs = context, targets, states, documents, inventory
        self.targets_by_id = _buckets(targets, lambda t: t.target_id)
        self.targets_by_path = _buckets(targets, lambda t: t.canonical_path)
        self.states_by_id = _buckets(states, lambda s: s.target_id)
        self.entries_by_path = _buckets(inventory, lambda e: e.current.path)
        self.documents_by_path = _buckets(documents, lambda d: d.source_path)


def _semantic(value):
    if hasattr(value, "model_dump"):
        if isinstance(value, (InlineExactContent, OpaqueContent)):
            return {"available_sha256": content_sha(value)}
        result = {
            name: _semantic(getattr(value, name))
            for name in type(value).model_fields
            if name not in ("file_roles", "resource_origin", "relationship_heading")
            or getattr(value, name) is not None
        }
        if isinstance(value, ReferenceTarget):
            result["representations"] = sorted(set(value.representations))
        elif isinstance(value, LinkQuery):
            result["spellings"] = sorted(set(value.spellings))
        return result
    if isinstance(value, (list, tuple)):
        return [_semantic(item) for item in value]
    if isinstance(value, bytes):
        return {"bytes_sha256": sha256(value).hexdigest()}
    return value


def associated_link_reviews(facts, subject, subject_id, both_outputs, *, _links=None):
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
    from .review_links import consumed_context

    association = subject.attachment.current_target_id
    portions = []
    documents = ()
    for stage in ("current", "incoming"):
        targets = getattr(context, stage + "_targets")
        states = getattr(context, stage + "_target_facts")
        selected = tuple(
            d
            for d in getattr(context, stage + "_documents")
            if d.document_id in subject.attachment.affected_documents
            or any(
                (
                    meaning := resolve_occurrence(o, targets, states, context.inventory)
                    if _links is None
                    else _links.resolve(context, stage, o)
                ).target_id
                == association
                or association in meaning.candidates
                for o in d.occurrences
            )
        )
        documents += selected
        portions.append(
            consumed_context(
                selected,
                targets,
                states,
                context.inventory,
                target_ids=(association,),
            )
        )
    fingerprint = sha256(
        json.dumps(_semantic(portions), sort_keys=True).encode()
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
                    and same_content(state.content, output.content)
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


def _observed_existence(current, state):
    expected = (
        ("missing", "intentionally_uncreated")
        if current.existence == "absent"
        else (current.existence,)
    )
    return state.existence in expected


def _check_current_inventory(facts, context, scope):
    # Complete supplied scope is checked against the independently observed inventory.
    for state in context.current_target_facts:
        records = scope.targets_by_id.get(state.target_id, ())
        if len(records) != 1:
            return "link_context_invalid"
        if (
            records[0].kind != "tag"
            and state.existence == "present"
            and len(scope.entries_by_path.get(records[0].canonical_path, ())) != 1
        ):
            return "link_context_invalid"
    for entry in facts.identity_inventory:
        matching = scope.targets_by_path.get(entry.current.path, ())
        if len(matching) != 1:
            return "link_context_unavailable"
        (record,) = matching
        if record.identity is not None and record.identity != entry.identity:
            return "link_context_invalid"
        observed = scope.states_by_id.get(record.target_id, ())
        if (
            len(observed) != 1
            or not _observed_existence(entry.current, observed[0])
            or content_key(observed[0].content) != content_key(entry.current.content)
        ):
            return "link_context_invalid"
        if record.kind != "resource" and entry.current.existence == "present":
            docs = tuple(
                d
                for d in scope.documents_by_path.get(entry.current.path, ())
                if same_content(d.content, entry.current.content)
            )
            if len(docs) != 1:
                return "link_context_unavailable"
    return None


def _check_attachment_target(subject, context, association):
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
        or not _observed_existence(subject.current, state)
        or content_key(state.content) != content_key(subject.current.content)
    ):
        return "link_context_invalid"
    from .link_validation import validate_link_target_state

    try:
        validate_link_target_state(state, context.current_targets)
    except ValueError:
        return "link_current_unsafe"
    return None


def _check_affected_document(doc, facts, context):
    from .reference_targets import validate_targets

    entries = tuple(
        e for e in facts.identity_inventory if e.current.path == doc.source_path
    )
    if (
        len(entries) != 1
        or entries[0].current.content is None
        or not same_content(entries[0].current.content, doc.content)
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
    return None


def _check_affected_occurrences(doc, resolved, association, continuation):
    for occurrence, meaning in zip(doc.occurrences, resolved, strict=True):
        if occurrence.meaning != meaning:
            return "link_context_invalid"
        if (
            (meaning.target_id == association or association in meaning.candidates)
            and meaning.status not in SAFE_LINK_STATUSES
            and not (
                continuation is not None
                and meaning.status == "missing"
                and meaning.target_id == association
                and meaning.path == continuation.path
                and not meaning.candidates
            )
        ):
            return "link_current_unsafe"
    return None


def _check_current_documents(
    facts, subject, context, association, continuation, _links
):
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
            resolve_occurrence(
                o,
                context.current_targets,
                context.current_target_facts,
                context.inventory,
            )
            if _links is None
            else _links.resolve(context, "current", o)
            for o in doc.occurrences
        )
        affected |= any(
            m.target_id == association or association in m.candidates for m in resolved
        )
        if not affected:
            continue
        problem = _check_affected_document(doc, facts, context)
        if problem is None:
            problem = _check_affected_occurrences(
                doc, resolved, association, continuation
            )
        if problem is not None:
            return problem
    return None


def validate_current_link_context(facts, subject, *, _links=None):
    """Bind current observations before any remembered or explicit preservation."""
    from .reversals import cleanup_removal_continuation

    continuation = cleanup_removal_continuation(facts, subject)
    if subject.attachment is None:
        return None
    context = facts.link_context
    if context is None or context.inventory != "complete":
        return "link_context_unavailable"
    association = subject.attachment.current_target_id
    scope = (
        _CurrentScope(
            context,
            context.current_targets,
            context.current_target_facts,
            context.current_documents,
            facts.identity_inventory,
        )
        if _links is None
        else _links.current_scope(context, facts.identity_inventory)
    )

    problem = _check_current_inventory(facts, context, scope)
    if problem is not None:
        return problem
    problem = _check_attachment_target(subject, context, association)
    if problem is not None:
        return problem
    return _check_current_documents(
        facts, subject, context, association, continuation, _links
    )
