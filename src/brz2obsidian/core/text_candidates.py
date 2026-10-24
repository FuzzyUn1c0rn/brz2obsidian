"""Selected explicit candidate consistency; no YAML, Markdown or path parsing."""

from brz2obsidian.contracts import LinkValidationBaseline, ReferenceTarget
from brz2obsidian.core.link_validation import validate_link_document
from brz2obsidian.core.reference_targets import validate_targets


def _target_meaning(target):
    return target.target_id, target.identity, target.canonical_path, target.target


def _known_memberships(subject, document, choice, *, mapping_choice):
    comparison = subject.structure
    if comparison is None:
        return True
    known = (comparison.current, comparison.original, comparison.incoming)
    if choice in ("current", "incoming"):
        selected = comparison.current if choice == "current" else comparison.incoming
        appearance = next(
            (f for f in selected.fields if f.key == selected.appearance_field), None
        )
        if appearance is not None and (
            not document.appearance_present or document.appearance != appearance.value
        ):
            return False
        expected = {
            (m.field_key, m.kind): tuple(
                (e.representation, _target_meaning(e.target)) for e in m.entries
            )
            for m in selected.memberships
        }
        actual = {
            (p.key, p.membership_kind): tuple(
                (r, _target_meaning(t))
                for r, t in zip(p.representations, p.targets, strict=True)
            )
            for p in document.properties
            if p.membership_kind
        }
        if selected.status == "supported" and actual != expected:
            return False
        return not any(actual.get(key) != value for key, value in expected.items())
    for prop in document.properties:
        if prop.membership_kind is None:
            continue
        for representation, target in zip(
            prop.representations, prop.targets, strict=True
        ):
            prior = next(
                (
                    tuple(
                        e.target
                        for m in d.memberships
                        if m.kind == prop.membership_kind and m.field_key == prop.key
                        for e in m.entries
                        if e.representation == representation
                    )
                    for d in known
                    if any(
                        e.representation == representation
                        for m in d.memberships
                        if m.kind == prop.membership_kind and m.field_key == prop.key
                        for e in m.entries
                    )
                ),
                (),
            )
            if not prior or any(
                _target_meaning(t) == _target_meaning(target) for t in prior
            ):
                continue
            offered = tuple(
                e.target
                for m in comparison.incoming.memberships
                if m.kind == prop.membership_kind and m.field_key == prop.key
                for e in m.entries
                if e.representation == representation
            )
            mapped = {
                m.target_id
                for m in comparison.incoming_mappings
                if m.kind == prop.membership_kind
            }
            if (
                not mapping_choice
                or target.target_id not in mapped
                or not any(
                    _target_meaning(t) == _target_meaning(target) for t in offered
                )
            ):
                return False
    return True


def validate_text_candidate(facts, change, candidate, choice, *, mapping_choice=False):
    subject = next(
        s
        for s in facts.subjects
        if (s.item_id, s.facet) == (change.item_id, change.facet)
    )
    document = candidate.document
    owner = (
        facts.incoming_identity.collection_id,
        facts.incoming_identity.module_id,
        change.item_id,
    )
    if (
        (
            candidate.identity.collection_id,
            candidate.identity.module_id,
            candidate.identity.item_id,
        )
        != owner
        or candidate.status != "safe"
        or document.status != "safe"
        or document.content.data != candidate.content.data
        or document.body.end != len(candidate.content.data)
        or document.output_format
        != (
            facts.baseline_identity.output_format
            if choice == "current"
            else facts.incoming_identity.output_format
        )
    ):
        return False
    selected = (
        change.current
        if choice == "current"
        else change.incoming
        if choice == "incoming"
        else candidate.content
    )
    if selected is None or selected.data != candidate.content.data:
        return False
    baseline = None
    context = facts.link_context
    if context is not None and change.current is not None:
        candidates = tuple(
            d
            for d in context.current_documents
            if d.document_id == candidate.links.document_id
            and d.source_path == change.target_path
            and d.content.data == change.current.data
        )
        if len(candidates) == 1:
            baseline = LinkValidationBaseline(
                schema_id="brz2obsidian.link-validation-baseline",
                schema_version=1,
                document=candidates[0],
                targets=context.current_targets,
                target_facts=context.current_target_facts,
                inventory=context.inventory,
            )
    if not validate_link_document(
        candidate.links,
        expected_content=candidate.content,
        expected_path=change.target_path,
        targets=candidate.link_targets,
        target_facts=candidate.link_target_facts,
        inventory=candidate.links.inventory,
        baseline=baseline,
    ).valid:
        return False
    if any(
        t.identity is not None and t.identity != candidate.identity
        for t in candidate.link_targets
        if t.canonical_path == change.target_path
    ):
        return False
    try:
        validate_targets(
            (
                ReferenceTarget(
                    schema_id="brz2obsidian.reference-target",
                    schema_version=1,
                    target_id=change.subject_id,
                    kind="relationship",
                    canonical_path=change.target_path,
                    identity=candidate.identity,
                    target=candidate.target,
                    representations=(change.subject_id,),
                    validation_fingerprint=candidate.validation_fingerprint,
                    status=candidate.status,
                ),
            )
        )
        keys = [p.key for p in document.properties]
        if len(set(keys)) != len(keys):
            return False
        components = [
            p.identity_component
            for p in document.properties
            if p.identity_component is not None
        ]
        if len(set(components)) != len(components):
            return False
        expected = dict(zip(("collection", "module", "item"), owner, strict=True))
        end = 0
        declared = set()
        category_representations = set()
        for prop in document.properties:
            if (
                prop.span.start < end
                or prop.span.end > document.body.start
                or candidate.content.data[prop.span.start : prop.span.end] != prop.raw
            ):
                return False
            end = prop.span.end
            if prop.identity_component is not None:
                if prop.identity_value != expected[prop.identity_component]:
                    return False
                declared.add((prop.key, prop.identity_component))
            if prop.membership_kind:
                if len(prop.representations) != len(prop.targets) or any(
                    t.kind != prop.membership_kind or r not in t.representations
                    for r, t in zip(prop.representations, prop.targets, strict=True)
                ):
                    return False
                validate_targets(prop.targets)
                if prop.membership_kind == "category":
                    category_representations.update(
                        r for t in prop.targets for r in t.representations
                    )
        if not _known_memberships(
            subject, document, choice, mapping_choice=mapping_choice
        ):
            return False
        if subject.structure is not None:
            required = {
                (f.key, f.identity_component)
                for d in (
                    subject.structure.original,
                    subject.structure.current,
                    subject.structure.incoming,
                )
                for f in d.fields
                if f.identity_component is not None
            }
            if not required <= declared:
                return False
        if (
            document.appearance
            and document.appearance not in category_representations
            and choice != "current"
        ):
            if subject.structure is None:
                return False
            local = subject.structure.current
            field = next(
                (f for f in local.fields if f.key == local.appearance_field), None
            )
            previously_valid = any(
                field and field.value in e.target.representations
                for m in local.memberships
                if m.kind == "category"
                for e in m.entries
            )
            if field is None or field.value != document.appearance or previously_valid:
                return False
    except ValueError:
        return False
    return True
