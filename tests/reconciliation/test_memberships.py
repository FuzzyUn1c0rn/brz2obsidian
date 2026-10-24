"""Literal membership and owned-section expectations at public seams."""

from brz2obsidian.contracts import ExactContent
from brz2obsidian.core import reconcile
from brz2obsidian.obsidian import align_structure, interpret_structure
from tests.reconciliation.test_proposals import request


def target(target_id, kind, *representations):
    from brz2obsidian.contracts import (
        IdentityTargetFacts,
        ImportedItemIdentity,
        ReferenceTarget,
    )

    return ReferenceTarget(
        schema_id="brz2obsidian.reference-target",
        schema_version=1,
        target_id=target_id,
        kind=kind,
        representations=representations,
        canonical_path=None if kind == "tag" else "Targets/" + target_id + ".md",
        identity=ImportedItemIdentity(
            collection_id="folio:collection",
            module_id="synthetic-folio",
            item_id=target_id,
        )
        if kind in ("category", "relationship")
        else None,
        target=None
        if kind == "tag"
        else IdentityTargetFacts(
            normalized_path="targets/" + target_id.casefold() + ".md",
            containment="contained",
            status="safe",
        ),
        validation_fingerprint="validated:" + target_id,
        status="safe",
    )


def membership_request(original, current, incoming, *, targets, **options):
    facts = request(original=original, current=current, incoming=incoming)
    docs = tuple(
        interpret_structure(
            ExactContent(data=data), output_format=7, membership_targets=targets
        )
        for data in (original, current, incoming)
    )
    comparison = align_structure(*docs, **options)
    return facts.model_copy(
        update={
            "subjects": (
                facts.subjects[0].model_copy(update={"structure": comparison}),
            )
        }
    )


def test_additive_memberships_preserve_local_order_aliases_appearance_and_prose():
    original = b'---\ncategories:\n  - "[[A]]"\ntags:\n  - alpha\nappearance_category: "[[A]]"\n---\nOriginal.\n'
    current = b'---\ncategories:\n  - "[[C|Local label]]"\n  - "[[A]]"\ntags:\n  - local\n  - alpha\nappearance_category: "[[C|Local label]]"\n---\nAuthored prose.\n'
    incoming = b'---\ncategories:\n  - "[[A]]"\n  - "[[B]]"\ntags:\n  - alpha\n  - beta\nappearance_category: "[[B]]"\n---\nOriginal.\n'
    targets = (
        target("a", "category", "[[A]]"),
        target("b", "category", "[[B]]"),
        target("c", "category", "[[C|Local label]]"),
        target("alpha", "tag", "alpha"),
        target("beta", "tag", "beta"),
        target("local", "tag", "local"),
    )
    change = reconcile(
        membership_request(original, current, incoming, targets=targets)
    ).changes[0]
    assert change.disposition == "compatible"
    assert (
        change.result.data
        == b'---\ncategories:\n  - "[[C|Local label]]"\n  - "[[A]]"\n  - "[[B]]"\ntags:\n  - local\n  - alpha\n  - beta\nappearance_category: "[[C|Local label]]"\n---\nAuthored prose.\n'
    )
    assert change.structure_result.appearance_field == "appearance_category"
    assert [e.target_id for e in change.structure_result.memberships[0].entries] == [
        "c",
        "a",
        "b",
    ]
    assert change.requires_decision


def test_empty_membership_accepts_additions_and_mapping_survives_source_rename():
    from brz2obsidian.contracts import ClassificationMapping

    original = b'---\ncategories: []\nappearance_category: ""\n---\nText.\n'
    incoming = (
        b'---\ncategories:\n  - "[[B]]"\nappearance_category: "[[B]]"\n---\nText.\n'
    )
    mapping = ClassificationMapping(
        schema_id="brz2obsidian.classification-mapping",
        schema_version=1,
        classification_id="source:b",
        target_id="b",
        kind="category",
        source_label="Old name",
    )
    renamed = mapping.model_copy(update={"source_label": "Renamed"})
    facts = membership_request(
        original,
        original,
        incoming,
        targets=(target("b", "category", "[[B]]"),),
        prior_mappings=(mapping,),
        incoming_mappings=(renamed,),
    )
    change = reconcile(facts).changes[0]
    assert change.disposition == "compatible"
    assert (
        change.result.data
        == b'---\ncategories:\n  - "[[B]]"\nappearance_category: ""\n---\nText.\n'
    )
    comparison = facts.subjects[0].structure
    assert (
        comparison.prior_mappings[0].classification_id
        == comparison.incoming_mappings[0].classification_id
    )


def test_independent_owned_relationship_and_resource_sections_combine_exactly():
    current = b"Authored intro.\n## Related\n\n- [[Local|Alias]]\n\n## Resources\n\n- [[file.pdf]]\n"
    incoming = b"Intro.\n## Related\n\n- [[Old]]\n\n## Resources\n\n- [[new.pdf]]\n"
    change = reconcile(owned_request(current, incoming)).changes[0]
    assert change.disposition == "compatible"
    assert (
        change.result.data
        == b"Authored intro.\n## Related\n\n- [[Local|Alias]]\n\n## Resources\n\n- [[new.pdf]]\n"
    )
    assert [
        (s.section_id, s.entries) for s in change.structure_result.owned_sections
    ] == [("related", ("[[Local|Alias]]",)), ("resources", ("[[new.pdf]]",))]


def test_membership_registry_cannot_authorize_plain_or_external_category_syntax():
    for representation in (
        "https://example.test/category",
        "Plain category",
        "![[Embedded]]",
        "[[../Escape]]",
    ):
        import json

        original = b"---\ncategories: []\n---\nText.\n"
        incoming = (
            "---\ncategories:\n  - " + json.dumps(representation) + "\n---\nText.\n"
        ).encode()
        facts = membership_request(
            original,
            original,
            incoming,
            targets=(target("bad", "category", representation),),
        )
        change = reconcile(facts).changes[0]
        assert change.disposition == "unresolved" and change.result is None
        assert change.original.data == original and change.incoming.data == incoming


def test_invalid_existing_appearance_is_reported_without_blocking_safe_addition():
    original = b'---\ncategories:\n  - "[[A]]"\nappearance_category: "[[Absent]]"\n---\nText.\n'
    incoming = b'---\ncategories:\n  - "[[A]]"\n  - "[[B]]"\nappearance_category: "[[A]]"\n---\nText.\n'
    change = reconcile(
        membership_request(
            original,
            original,
            incoming,
            targets=(
                target("a", "category", "[[A]]"),
                target("b", "category", "[[B]]"),
            ),
        )
    ).changes[0]
    assert change.disposition == "compatible"
    assert b'appearance_category: "[[Absent]]"' in change.result.data
    assert change.structure_result.issues == ("appearance_not_member",)


def test_membership_unknown_unsafe_and_duplicate_semantics_keep_exact_alternatives():
    original = b'---\ncategories:\n  - "[[A]]"\n---\nText.\n'
    changed = b'---\ncategories:\n  - "[[A]]"\n  - "[[B]]"\n---\nText.\n'
    cases = (
        ((target("a", "category", "[[A]]"),), changed),
        (
            (
                target("a", "category", "[[A]]"),
                target("b", "category", "[[B]]").model_copy(
                    update={"status": "unsafe"}
                ),
            ),
            changed,
        ),
        (
            (target("a", "category", "[[A]]", "[[A|Alias]]"),),
            b'---\ncategories:\n  - "[[A]]"\n  - "[[A|Alias]]"\n---\nText.\n',
        ),
        ((target("a", "category", "[[A]]"), target("a", "category", "[[B]]")), changed),
    )
    for targets, incoming in cases:
        result = reconcile(
            membership_request(original, original, incoming, targets=targets)
        )
        change = result.changes[0]
        assert (
            change.disposition == "unresolved"
            and change.result is None
            and not result.ready
        )
        assert change.original.data == change.current.data == original
        assert change.incoming.data == incoming


def test_source_removal_or_mapping_remap_never_overwrites_local_memberships():
    from brz2obsidian.contracts import ClassificationMapping

    original = b'---\ncategories:\n  - "[[A]]"\n  - "[[B]]"\nappearance_category: "[[B]]"\n---\nText.\n'
    current = b'---\ncategories:\n  - "[[C]]"\n  - "[[B]]"\n  - "[[A]]"\nappearance_category: "[[B]]"\n---\nText.\n'
    removal = (
        b'---\ncategories:\n  - "[[A]]"\nappearance_category: "[[A]]"\n---\nText.\n'
    )
    targets = tuple(
        target(v.lower(), "category", "[[" + v + "]]") for v in ("A", "B", "C")
    )
    mapping = ClassificationMapping(
        schema_id="brz2obsidian.classification-mapping",
        schema_version=1,
        classification_id="source:b",
        target_id="b",
        kind="category",
        source_label="B",
    )
    cases = (
        (removal, (), ()),
        (
            original.replace(b"Text.", b"Source prose."),
            (mapping,),
            (mapping.model_copy(update={"target_id": "c"}),),
        ),
    )
    for incoming, prior, upcoming in cases:
        result = reconcile(
            membership_request(
                original,
                current,
                incoming,
                targets=targets,
                prior_mappings=prior,
                incoming_mappings=upcoming,
            )
        )
        change = result.changes[0]
        assert (
            change.disposition == "unresolved"
            and change.provenance.rule == "structure_conflict"
        )
        assert change.current.data == current and change.incoming.data == incoming
        assert change.requires_decision and not result.ready


def test_local_membership_removal_and_source_order_do_not_reintroduce_removed_entry():
    original = b'---\ncategories:\n  - "[[A]]"\n  - "[[B]]"\n---\nText.\n'
    current = b'---\ncategories:\n  - "[[B|Local alias]]"\n---\nText.\n'
    incoming = b'---\ncategories:\n  - "[[B]]"\n  - "[[A]]"\n  - "[[C]]"\n---\nText.\n'
    targets = (
        target("a", "category", "[[A]]"),
        target("b", "category", "[[B]]", "[[B|Local alias]]"),
        target("c", "category", "[[C]]"),
    )
    change = reconcile(
        membership_request(original, current, incoming, targets=targets)
    ).changes[0]
    assert (
        change.result.data
        == b'---\ncategories:\n  - "[[B|Local alias]]"\n  - "[[C]]"\n---\nText.\n'
    )


def owned_request(current, incoming, *, original=None, membership_targets=()):
    from brz2obsidian.contracts import GeneratedSectionBasis, StructureSpan
    from tests.reconciliation.test_proposals import identity

    if original is None:
        original = (
            b"Intro.\n## Related\n\n- [[Old]]\n\n## Resources\n\n- [[file.pdf]]\n"
        )
    boundary = original.index(b"## Resources")
    bases = tuple(
        GeneratedSectionBasis(
            schema_id="brz2obsidian.generated-section-basis",
            schema_version=1,
            original=ExactContent(data=original),
            output_identity=identity(),
            source_version="source:a",
            item_id="entry:opening",
            facet="content",
            section_id=section_id,
            kind=kind,
            span=StructureSpan(start=start, end=end),
            heading=heading,
            generation_fingerprint="renderer7:" + section_id,
        )
        for section_id, kind, start, end, heading in (
            (
                "related",
                "relationship",
                original.index(b"## Related"),
                boundary,
                b"## Related",
            ),
            ("resources", "resource", boundary, len(original), b"## Resources"),
        )
    )
    docs = tuple(
        interpret_structure(
            ExactContent(data=data),
            output_format=7,
            section_bases=bases,
            section_targets=known_section_targets(),
            membership_targets=membership_targets,
        )
        for data in (original, current, incoming)
    )
    facts = request(original=original, current=current, incoming=incoming)
    return facts.model_copy(
        update={
            "subjects": (
                facts.subjects[0].model_copy(
                    update={"structure": align_structure(*docs, section_bases=bases)}
                ),
            )
        }
    )


def test_owned_section_divergence_duplicate_boundaries_and_unsupported_links_refuse():
    original = b"Intro.\n## Related\n\n- [[Old]]\n\n## Resources\n\n- [[file.pdf]]\n"
    local = original.replace(b"[[Old]]", b"[[Local]]")
    cases = (
        original.replace(b"[[Old]]", b"[[Source]]"),
        original + b"\n## Related\n\n- [[Duplicate]]\n",
        original.replace(b"[[file.pdf]]", b"[[file.pdf]]\n- [[file.pdf|Duplicate]]"),
        original.replace(b"[[file.pdf]]", b"[External](https://example.test/file)"),
        original.replace(b"## Resources", b"## Renamed resources"),
    )
    for incoming in cases:
        result = reconcile(owned_request(local, incoming))
        change = result.changes[0]
        assert change.disposition == "unresolved" and change.result is None
        assert (
            change.current.data == local
            and change.original.data == original
            and change.incoming.data == incoming
        )
        assert not result.ready


def test_heading_alone_and_wrong_generation_binding_never_establish_section_ownership():
    original = b"Intro.\n## Related\n\n- [[Old]]\n\n## Resources\n\n- [[file.pdf]]\n"
    incoming = original.replace(b"file.pdf", b"new.pdf")
    facts = owned_request(original, incoming)
    comparison = facts.subjects[0].structure
    variants = (
        comparison.model_copy(update={"section_bases": ()}),
        comparison.model_copy(
            update={
                "section_bases": tuple(
                    b.model_copy(update={"source_version": "unrelated:source"})
                    for b in comparison.section_bases
                )
            }
        ),
    )
    for comparison in variants:
        result = reconcile(
            facts.model_copy(
                update={
                    "subjects": (
                        facts.subjects[0].model_copy(update={"structure": comparison}),
                    )
                }
            )
        )
        assert result.changes[0].disposition == "unresolved" and not result.ready
    docs = tuple(
        interpret_structure(ExactContent(data=data), output_format=7)
        for data in (original, original, incoming)
    )
    comparison = align_structure(*docs)
    result = reconcile(
        facts.model_copy(
            update={
                "subjects": (
                    facts.subjects[0].model_copy(update={"structure": comparison}),
                )
            }
        )
    )
    assert result.changes[0].provenance.rule in (
        "structure_unsupported",
        "structure_ambiguous",
    )


def test_partial_normalized_section_edits_cannot_evade_atomic_section_conflict():
    from brz2obsidian.contracts import StructureByteEdit, StructureSpan

    original = b"Intro.\n## Related\n\n- [[Old]]\n\n## Resources\n\n- [[file.pdf]]\n"
    current, incoming = (
        original.replace(b"Old", b"Local"),
        original.replace(b"file.pdf", b"new.pdf"),
    )
    facts = owned_request(current, incoming)
    comparison = facts.subjects[0].structure
    position = original.index(b"file.pdf")
    partial = StructureByteEdit(
        span=StructureSpan(start=position, end=position + 8),
        expected=b"file.pdf",
        replacement=b"new.pdf",
    )
    comparison = comparison.model_copy(update={"source_edits": (partial,)})
    result = reconcile(
        facts.model_copy(
            update={
                "subjects": (
                    facts.subjects[0].model_copy(update={"structure": comparison}),
                )
            }
        )
    )
    assert result.changes[0].provenance.rule == "structure_unbound" and not result.ready


def test_scoped_membership_assumptions_ignore_source_label_but_track_target_validation():
    from brz2obsidian.contracts import ClassificationMapping

    original = b"---\ncategories: []\n---\nText.\n"
    incoming = b'---\ncategories:\n  - "[[B]]"\n---\nText.\n'
    mapping = ClassificationMapping(
        schema_id="brz2obsidian.classification-mapping",
        schema_version=1,
        classification_id="source:b",
        target_id="b",
        kind="category",
        source_label="Old",
    )
    targets = (target("b", "category", "[[B]]"),)
    first = membership_request(
        original,
        original,
        incoming,
        targets=targets,
        prior_mappings=(mapping,),
        incoming_mappings=(mapping,),
    )
    renamed = membership_request(
        original,
        original,
        incoming,
        targets=targets,
        prior_mappings=(mapping,),
        incoming_mappings=(mapping.model_copy(update={"source_label": "Renamed"}),),
    )
    revalidated = membership_request(
        original,
        original,
        incoming,
        targets=(
            targets[0].model_copy(
                update={"validation_fingerprint": "validation:changed"}
            ),
        ),
        prior_mappings=(mapping,),
        incoming_mappings=(mapping,),
    )
    fingerprints = [
        next(
            a.fingerprint
            for a in reconcile(f).changes[0].assumptions
            if a.kind == "structure"
        )
        for f in (first, renamed, revalidated)
    ]
    assert fingerprints[0] == fingerprints[1]
    assert fingerprints[0] != fingerprints[2]


def test_source_neutral_membership_facts_combine_without_obsidian_syntax():
    from brz2obsidian.contracts import (
        MembershipEntry,
        MembershipSet,
        StructureComparison,
        StructuredDocument,
        StructureField,
        StructureSpan,
    )

    original = b"roles:\n + first\n"
    current = b"roles:\n + local\n + first\n"
    incoming = b"roles:\n + first\n + source\n"
    docs = []
    for raw, values in (
        (original, ("first",)),
        (current, ("local", "first")),
        (incoming, ("first", "source")),
    ):
        entries = tuple(
            MembershipEntry(
                target=target(v, "tag", v),
                representation=v,
                raw=(" + " + v + "\n").encode(),
            )
            for v in values
        )
        docs.append(
            StructuredDocument(
                schema_id="brz2obsidian.structured-document",
                schema_version=1,
                output_format=7,
                content=ExactContent(data=raw),
                status="supported",
                issues=(),
                fields=(
                    StructureField(
                        key="roles",
                        kind="opaque",
                        identity_component=None,
                        value=None,
                        scalar_type="opaque",
                        span=StructureSpan(start=0, end=len(raw)),
                        value_span=StructureSpan(start=6, end=6),
                    ),
                ),
                body=StructureSpan(start=len(raw), end=len(raw)),
                appearance_field=None,
                owned_sections=(),
                memberships=(
                    MembershipSet(
                        field_key="roles",
                        kind="tag",
                        prefix=b"roles:\n",
                        entries=entries,
                    ),
                ),
            )
        )
    comparison = StructureComparison(
        schema_id="brz2obsidian.structure-comparison",
        schema_version=1,
        original=docs[0],
        current=docs[1],
        incoming=docs[2],
        alignment="supported",
        issues=(),
        local_edits=(),
        source_edits=(),
        prior_mappings=(),
        incoming_mappings=(),
        section_bases=(),
    )
    facts = request(original=original, current=current, incoming=incoming)
    facts = facts.model_copy(
        update={
            "subjects": (
                facts.subjects[0].model_copy(update={"structure": comparison}),
            )
        }
    )
    change = reconcile(facts).changes[0]
    assert change.disposition == "compatible"
    assert change.result.data == b"roles:\n + local\n + first\n + source\n"


def test_support_roles_share_membership_preservation_but_configuration_requires_choice():
    original = (
        b'---\ncategories:\n  - "[[A]]"\nappearance_category: "[[A]]"\n---\nText.\n'
    )
    current = (
        b'---\ncategories:\n  - "[[A]]"\nappearance_category: ""\n---\nLocal text.\n'
    )
    incoming = b'---\ncategories:\n  - "[[A]]"\n  - "[[B]]"\nappearance_category: "[[B]]"\n---\nText.\n'
    targets = (target("a", "category", "[[A]]"), target("b", "category", "[[B]]"))
    facts = membership_request(original, current, incoming, targets=targets)
    for role in ("dashboard", "template", "guide", "configuration"):
        result = reconcile(
            facts.model_copy(
                update={
                    "subjects": (
                        facts.subjects[0].model_copy(update={"output_role": role}),
                    )
                }
            )
        )
        change = result.changes[0]
        if role == "configuration":
            assert (
                change.disposition == "unresolved" and change.structure_result is None
            )
            assert change.format_review.configuration_choice
        else:
            assert change.disposition == "compatible"
            assert (
                change.result.data
                == b'---\ncategories:\n  - "[[A]]"\n  - "[[B]]"\nappearance_category: ""\n---\nLocal text.\n'
            )
        assert change.requires_decision and not result.ready


def test_same_basename_section_alias_requires_unique_validated_target_identity():
    original = b"Intro.\n## Related\n\n- [[Old]]\n\n## Resources\n\n- [[file.pdf]]\n"
    incoming = original.replace(b"[[Old]]", b"[[Same]]")
    facts = owned_request(original, incoming)
    bases = facts.subjects[0].structure.section_bases
    targets = (
        target("old", "relationship", "[[Old]]"),
        target("one", "relationship", "[[Same]]"),
        target("two", "relationship", "[[Same]]"),
        target("file", "resource", "[[file.pdf]]"),
    )
    docs = tuple(
        interpret_structure(
            ExactContent(data=data),
            output_format=7,
            section_bases=bases,
            section_targets=targets,
        )
        for data in (original, original, incoming)
    )
    comparison = align_structure(*docs, section_bases=bases)
    change = reconcile(
        facts.model_copy(
            update={
                "subjects": (
                    facts.subjects[0].model_copy(update={"structure": comparison}),
                )
            }
        )
    ).changes[0]
    assert change.disposition == "unresolved" and change.result is None


def known_section_targets():
    return (
        target("old", "relationship", "[[Old]]"),
        target("local", "relationship", "[[Local]]", "[[Local|Alias]]"),
        target("source", "relationship", "[[Source]]"),
        target("file", "resource", "[[file.pdf]]", "[[file.pdf|Duplicate]]"),
        target("new", "resource", "[[new.pdf]]"),
    )


def test_normalized_target_safety_identity_and_field_binding_are_independently_checked():
    original = b'---\ncategories:\n  - "[[A]]"\n---\nText.\n'
    incoming = b'---\ncategories:\n  - "[[A]]"\n  - "[[B]]"\n---\nText.\n'
    a, b = target("a", "category", "[[A]]"), target("b", "category", "[[B]]")
    bad_targets = (
        b.model_copy(
            update={
                "target": b.target.model_copy(
                    update={"normalized_path": "elsewhere/b.md"}
                )
            }
        ),
        b.model_copy(
            update={"target": b.target.model_copy(update={"containment": "outside"})}
        ),
        b.model_copy(
            update={
                "canonical_path": "Targets/CON.md",
                "target": b.target.model_copy(
                    update={"normalized_path": "targets/con.md"}
                ),
            }
        ),
        b.model_copy(
            update={
                "canonical_path": a.canonical_path + "/nested.md",
                "target": b.target.model_copy(
                    update={"normalized_path": a.target.normalized_path + "/nested.md"}
                ),
            }
        ),
        b.model_copy(update={"identity": a.identity}),
        b.model_copy(update={"canonical_path": a.canonical_path, "target": a.target}),
    )
    for bad in bad_targets:
        result = reconcile(
            membership_request(original, original, incoming, targets=(a, bad))
        )
        assert result.changes[0].disposition == "unresolved" and not result.ready
    facts = membership_request(original, original, incoming, targets=(a, b))
    comparison = facts.subjects[0].structure
    source = comparison.incoming
    membership = source.memberships[0]
    invalid = membership.model_copy(update={"prefix": b"invented: bytes\n"})
    comparison = comparison.model_copy(
        update={"incoming": source.model_copy(update={"memberships": (invalid,)})}
    )
    change = reconcile(
        facts.model_copy(
            update={
                "subjects": (
                    facts.subjects[0].model_copy(update={"structure": comparison}),
                )
            }
        )
    ).changes[0]
    assert change.provenance.rule == "structure_unbound" and change.result is None


def test_membership_authority_cannot_relabel_an_inconsistent_scalar_field():
    original = b"---\ncategories: []\n---\nText.\n"
    incoming = b'---\ncategories:\n  - "[[A]]"\n---\nText.\n'
    facts = membership_request(
        original, original, incoming, targets=(target("a", "category", "[[A]]"),)
    )
    comparison = facts.subjects[0].structure
    source = comparison.incoming
    field = source.fields[0].model_copy(
        update={"kind": "scalar", "scalar_type": "null"}
    )
    comparison = comparison.model_copy(
        update={"incoming": source.model_copy(update={"fields": (field,)})}
    )
    change = reconcile(
        facts.model_copy(
            update={
                "subjects": (
                    facts.subjects[0].model_copy(update={"structure": comparison}),
                )
            }
        )
    ).changes[0]
    assert change.disposition == "unresolved" and change.result is None


def test_combined_membership_candidate_rechecks_semantic_uniqueness():
    original = b'---\ncategories:\n  - "[[A]]"\n---\nText.\n'
    current = b'---\ncategories:\n  - "[[Local]]"\n  - "[[A]]"\n---\nText.\n'
    incoming = b'---\ncategories:\n  - "[[A]]"\n  - "[[B]]"\n---\nText.\n'
    a, b = target("a", "category", "[[A]]"), target("b", "category", "[[B]]")
    local = target("local", "category", "[[Local]]").model_copy(
        update={"identity": b.identity}
    )
    facts = membership_request(original, current, incoming, targets=(a, b, local))
    assert all(
        d.status == "supported"
        for d in (
            facts.subjects[0].structure.original,
            facts.subjects[0].structure.current,
            facts.subjects[0].structure.incoming,
        )
    )
    change = reconcile(facts).changes[0]
    assert change.disposition == "unresolved" and change.result is None
    assert change.current.data == current and change.incoming.data == incoming


def test_unicode_membership_and_scalar_splicing_rebinds_owned_section_offsets():
    original = '---\npriority: 1\ncategories:\n  - "[[A]]"\n---\nCafé intro.\n## Related\n\n- [[Old]]\n\n## Resources\n\n- [[file.pdf]]\n'.encode()
    current = '---\npriority: 1\ncategories:\n  - "[[A]]"\n---\nÉdité intro.\n## Related\n\n- [[Local|Alias]]\n\n## Resources\n\n- [[file.pdf]]\n'.encode()
    incoming = '---\npriority: 1000\ncategories:\n  - "[[A]]"\n  - "[[B]]"\n---\nCafé intro.\n## Related\n\n- [[Old]]\n\n## Resources\n\n- [[new.pdf]]\n'.encode()
    facts = owned_request(
        current,
        incoming,
        original=original,
        membership_targets=(
            target("a", "category", "[[A]]"),
            target("b", "category", "[[B]]"),
        ),
    )
    change = reconcile(facts).changes[0]
    assert change.disposition == "compatible"
    assert (
        change.result.data
        == '---\npriority: 1000\ncategories:\n  - "[[A]]"\n  - "[[B]]"\n---\nÉdité intro.\n## Related\n\n- [[Local|Alias]]\n\n## Resources\n\n- [[new.pdf]]\n'.encode()
    )
    for section in change.structure_result.owned_sections:
        assert change.result.data[section.span.start : section.span.end] == section.raw


def test_case_variant_duplicate_owned_heading_cannot_hide_in_unchanged_source_gap():
    original = b"Intro.\n## Related\n\n- [[Old]]\n\n## Resources\n\n- [[file.pdf]]\n"
    current = original + b"## related\n\n- [[Local]]\n"
    incoming = original.replace(b"[[Old]]", b"[[Source]]")
    change = reconcile(owned_request(current, incoming)).changes[0]
    assert change.disposition == "unresolved" and change.result is None


def test_real_keep_memory_and_explicit_keep_cannot_bypass_affected_target_safety():
    from tests.reconciliation.test_absence import choose, remembered

    original = b'---\ncategories:\n  - "[[A]]"\n---\nText.\n'
    current = b'---\ncategories:\n  - "[[A]]"\n---\nLocal prose.\n'
    incoming = b'---\ncategories:\n  - "[[A]]"\n  - "[[B]]"\n---\nText.\n'
    a, b = target("a", "category", "[[A]]"), target("b", "category", "[[B]]")
    safe = membership_request(original, current, incoming, targets=(a, b))
    memory = remembered(safe)
    outside = a.model_copy(
        update={"target": a.target.model_copy(update={"containment": "outside"})}
    )
    unsafe = membership_request(original, current, incoming, targets=(outside, b))
    assert reconcile(unsafe).changes[0].disposition == "unresolved"
    replayed = reconcile(unsafe.model_copy(update={"source_version_memory": (memory,)}))
    assert not replayed.ready and replayed.changes[0].disposition == "unresolved"
    assert replayed.changes[0].result is None
    assert replayed.changes[0].preservation_review.matched_memory_ids == ()
    offered = reconcile(unsafe)
    attempted = choose(unsafe, offered, "keep_vault")
    refused = reconcile(
        unsafe.model_copy(update={"preservation_decisions": (attempted,)})
    )
    assert not refused.ready and refused.changes[0].disposition == "refused"
    assert refused.changes[0].result is None and refused.source_version_memory == ()


def test_keep_memory_cannot_bypass_unbound_section_reference_or_target_facts():
    from tests.reconciliation.test_absence import remembered

    current = b"Authored intro.\n## Related\n\n- [[Local|Alias]]\n\n## Resources\n\n- [[file.pdf]]\n"
    incoming = b"Intro.\n## Related\n\n- [[Old]]\n\n## Resources\n\n- [[new.pdf]]\n"
    safe = owned_request(current, incoming)
    memory = remembered(safe)
    comparison = safe.subjects[0].structure
    local = comparison.current
    section = local.owned_sections[0]
    unknown = local.model_copy(
        update={
            "owned_sections": (
                section.model_copy(update={"section_id": "missing-basis"}),
            )
            + local.owned_sections[1:]
        }
    )
    unbound = local.model_copy(
        update={
            "owned_sections": (
                section.model_copy(update={"raw": section.raw + b"invented"}),
            )
            + local.owned_sections[1:]
        }
    )
    unsafe_target = section.targets[0].model_copy(
        update={
            "target": section.targets[0].target.model_copy(
                update={"containment": "outside"}
            )
        }
    )
    unsafe = local.model_copy(
        update={
            "owned_sections": (
                section.model_copy(update={"targets": (unsafe_target,)}),
            )
            + local.owned_sections[1:]
        }
    )
    variants = [
        comparison.model_copy(update={"current": d}) for d in (unknown, unbound, unsafe)
    ]
    variants.append(
        comparison.model_copy(
            update={
                "section_bases": tuple(
                    b.model_copy(update={"source_version": "unrelated"})
                    for b in comparison.section_bases
                )
            }
        )
    )
    variants.append(comparison.model_copy(update={"local_edits": ()}))
    for invalid in variants:
        facts = safe.model_copy(
            update={
                "subjects": (
                    safe.subjects[0].model_copy(update={"structure": invalid}),
                ),
                "source_version_memory": (memory,),
            }
        )
        result = reconcile(facts)
        assert not result.ready and result.changes[0].disposition == "unresolved"
        assert result.changes[0].result is None
        assert result.changes[0].preservation_review.matched_memory_ids == ()
        assert result.source_version_memory == (memory,)


def test_shared_safety_guard_keeps_safe_conflicts_opaque_bytes_and_existing_warning():
    from tests.reconciliation.test_absence import remembered

    original = b"Intro.\n## Related\n\n- [[Old]]\n\n## Resources\n\n- [[file.pdf]]\n"
    local = original.replace(b"[[Old]]", b"[[Local]]")
    incoming = original.replace(b"[[Old]]", b"[[Source]]")
    conflict = owned_request(local, incoming)
    assert reconcile(conflict).changes[0].disposition == "unresolved"
    conflict_memory = remembered(conflict)
    kept = reconcile(
        conflict.model_copy(update={"source_version_memory": (conflict_memory,)})
    )
    assert kept.ready and kept.changes[0].result.data == local
    assert kept.changes[0].structure_result is None

    old = b'---\ncategories:\n  - "[[A]]"\nappearance_category: "[[Absent]]"\n---\nText.\n'
    source = b'---\ncategories:\n  - "[[A]]"\n  - "[[B]]"\nappearance_category: "[[A]]"\n---\nText.\n'
    targets = (target("a", "category", "[[A]]"), target("b", "category", "[[B]]"))
    safe = membership_request(old, old, source, targets=targets)
    assert reconcile(safe).changes[0].structure_result.issues == (
        "appearance_not_member",
    )
    memory = remembered(safe)
    for current in (old, b"opaque local\xff\x00"):
        facts = membership_request(old, current, source, targets=targets)
        result = reconcile(
            facts.model_copy(update={"source_version_memory": (memory,)})
        )
        assert result.ready and result.changes[0].result.data == current
        assert result.changes[0].disposition == "preserve_vault"
        assert result.changes[0].structure_result is None


def test_unsafe_incoming_only_target_refuses_combination_but_allows_safe_exact_keep():
    from tests.reconciliation.test_absence import choose, remembered

    original = b'---\ncategories:\n  - "[[A]]"\n---\nText.\n'
    current = b'---\ncategories:\n  - "[[A]]"\n---\nLocal prose.\n'
    incoming = b'---\ncategories:\n  - "[[A]]"\n  - "[[B]]"\n---\nText.\n'
    a, b = target("a", "category", "[[A]]"), target("b", "category", "[[B]]")
    safe = membership_request(original, current, incoming, targets=(a, b))
    memory = remembered(safe)
    outside = b.model_copy(
        update={"target": b.target.model_copy(update={"containment": "outside"})}
    )
    facts = membership_request(original, current, incoming, targets=(a, outside))
    offered = reconcile(facts)
    assert offered.changes[0].disposition == "unresolved" and not offered.ready
    kept = reconcile(facts.model_copy(update={"source_version_memory": (memory,)}))
    assert kept.ready and kept.changes[0].result.data == current
    assert kept.changes[0].structure_result is None
    explicit = reconcile(
        facts.model_copy(
            update={"preservation_decisions": (choose(facts, offered, "keep_vault"),)}
        )
    )
    assert explicit.ready and explicit.changes[0].result.data == current
    assert explicit.changes[0].incoming.data == incoming

    local_section = b"Authored intro.\n## Related\n\n- [[Local|Alias]]\n\n## Resources\n\n- [[file.pdf]]\n"
    source_section = (
        b"Intro.\n## Related\n\n- [[Old]]\n\n## Resources\n\n- [[new.pdf]]\n"
    )
    section_facts = owned_request(local_section, source_section)
    section_memory = remembered(section_facts)
    comparison = section_facts.subjects[0].structure
    document = comparison.incoming
    resource = document.owned_sections[1]
    bad_target = resource.targets[0].model_copy(
        update={
            "target": resource.targets[0].target.model_copy(
                update={"containment": "outside"}
            )
        }
    )
    document = document.model_copy(
        update={
            "owned_sections": (
                document.owned_sections[0],
                resource.model_copy(update={"targets": (bad_target,)}),
            )
        }
    )
    section_facts = section_facts.model_copy(
        update={
            "subjects": (
                section_facts.subjects[0].model_copy(
                    update={
                        "structure": comparison.model_copy(
                            update={"incoming": document}
                        )
                    }
                ),
            )
        }
    )
    assert reconcile(section_facts).changes[0].disposition == "unresolved"
    kept_section = reconcile(
        section_facts.model_copy(update={"source_version_memory": (section_memory,)})
    )
    assert kept_section.ready and kept_section.changes[0].result.data == local_section
