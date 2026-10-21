"""Literal structure expectations through public interpretation and reconciliation."""

from brz2obsidian.contracts import ExactContent
from brz2obsidian.obsidian import interpret_structure


def test_format7_interpretation_binds_scalar_identity_and_exact_byte_spans():
    content = ExactContent(
        data=b'---\r\npriority: 1\r\nsource_item_id: "entry:opening"\r\n---\r\nFirst paragraph.\r\n'
    )
    result = interpret_structure(content, output_format=7)
    assert result.schema_id == "brz2obsidian.structured-document"
    assert result.schema_version == 1
    assert result.output_format == 7 and result.status == "supported"
    assert [(f.key, f.kind, f.value) for f in result.fields] == [
        ("priority", "scalar", 1),
        ("source_item_id", "identity", "entry:opening"),
    ]
    field = result.fields[0]
    assert content.data[field.span.start : field.span.end] == b"priority: 1\r\n"
    assert (
        result.content.data[result.body.start : result.body.end]
        == b"First paragraph.\r\n"
    )


def structured_request(original, current, incoming):
    from brz2obsidian.obsidian import align_structure
    from tests.reconciliation.test_proposals import request

    facts = request(original=original, current=current, incoming=incoming)
    documents = tuple(
        interpret_structure(ExactContent(data=data), output_format=7)
        for data in (original, current, incoming)
    )
    subject = facts.subjects[0].model_copy(
        update={"structure": align_structure(*documents)}
    )
    return facts.model_copy(update={"subjects": (subject,)})


def test_independent_scalars_combine_at_current_spans_and_preserve_authored_body():
    from brz2obsidian.core import reconcile

    original = b'---\npriority: 1\nowner: "source"\ntags: []\n---\nOriginal prose.\n'
    current = b'---\r\npriority: 1\r\nowner: "local"\r\ntags: []\r\nextra: "keep"\r\n---\r\nAuthored prose.\xc3\xa9'
    incoming = b'---\npriority: 2\nowner: "source"\ntags: []\n---\nOriginal prose.\n'
    result = reconcile(structured_request(original, current, incoming))
    (change,) = result.changes
    assert change.disposition == "compatible" and change.requires_decision
    assert (
        change.result.data
        == b'---\r\npriority: 2\r\nowner: "local"\r\ntags: []\r\nextra: "keep"\r\n---\r\nAuthored prose.\xc3\xa9'
    )
    assert change.provenance.producer == "structure/v1"
    assert change.provenance.rule == "structure_combined"
    assert not result.ready


def test_changed_unsupported_documents_keep_exact_whole_file_alternatives():
    from brz2obsidian.core import reconcile

    bad_documents = (
        b"---\npriority: 1\npriority: 2\n---\nText.\n",
        b"---\npriority: &shared 1\n---\nText.\n",
        b"---\npriority: {nested: value}\n---\nText.\n",
        b"---\npriority: !custom value\n---\nText.\n",
        b"---\npriority: |\n  multi\n---\nText.\n",
        b"---\npriority: 1\nText without closing frontmatter.\n",
        b"---\npriority: 1\n",
        b"---\nsource_item_id:\n---\nText.\n",
        b"--- \npriority: 1\n---\nText.\n",
        b"\xef\xbb\xbfText.\n",
        b"Text.\x00\n",
        b"Text.\xff\n",
    )
    for original in bad_documents:
        incoming = original + b"Source change.\n"
        interpreted = interpret_structure(ExactContent(data=original), output_format=7)
        assert interpreted.status in ("unsupported", "opaque")
        result = reconcile(structured_request(original, original, incoming))
        change = result.changes[0]
        assert change.disposition == "unresolved" and change.result is None
        assert change.original.data == change.current.data == original
        assert change.incoming.data == incoming
        assert not result.ready


def test_source_neutral_edits_combine_through_core_without_obsidian_interpretation():
    from brz2obsidian.contracts import (
        StructureByteEdit,
        StructureComparison,
        StructuredDocument,
        StructureSpan,
    )
    from brz2obsidian.core import reconcile
    from tests.reconciliation.test_proposals import request

    original = b"First old.\nMiddle.\nLast old.\n"
    current = b"First local.\nMiddle.\nLast old.\n"
    incoming = b"First old.\nMiddle.\nLast source.\n"
    facts = request(original=original, current=current, incoming=incoming)
    docs = tuple(
        StructuredDocument(
            schema_id="brz2obsidian.structured-document",
            schema_version=1,
            output_format=7,
            content=ExactContent(data=data),
            status="supported",
            issues=(),
            fields=(),
            body=StructureSpan(start=0, end=len(data)),
        )
        for data in (original, current, incoming)
    )
    comparison = StructureComparison(
        schema_id="brz2obsidian.structure-comparison",
        schema_version=1,
        original=docs[0],
        current=docs[1],
        incoming=docs[2],
        alignment="supported",
        issues=(),
        local_edits=(
            StructureByteEdit(
                span=StructureSpan(start=0, end=11),
                expected=b"First old.\n",
                replacement=b"First local.\n",
            ),
        ),
        source_edits=(
            StructureByteEdit(
                span=StructureSpan(start=19, end=29),
                expected=b"Last old.\n",
                replacement=b"Last source.\n",
            ),
        ),
    )
    subject = facts.subjects[0].model_copy(update={"structure": comparison})
    result = reconcile(facts.model_copy(update={"subjects": (subject,)}))
    change = result.changes[0]
    assert change.disposition == "compatible"
    assert change.result.data == b"First local.\nMiddle.\nLast source.\n"
    assert change.structure_result.content.data == change.result.data


def test_outer_unicode_byte_alignment_combines_independent_prose_edits():
    from brz2obsidian.core import reconcile

    original = "α old.\nMiddle.\nLast shared phrase.\n".encode()
    current = "α local café.\nMiddle.\nLast shared phrase.\n".encode()
    incoming = "α old.\nMiddle.\nLast source shared phrase.\n".encode()
    result = reconcile(structured_request(original, current, incoming))
    change = result.changes[0]
    assert change.disposition == "compatible"
    assert (
        change.result.data
        == "α local café.\nMiddle.\nLast source shared phrase.\n".encode()
    )
    assumption = next(a for a in change.assumptions if a.kind == "structure")
    assert assumption.fingerprint


def test_overlapping_prose_divergent_scalars_and_identity_changes_remain_unresolved():
    from brz2obsidian.core import reconcile

    cases = (
        (
            b"One.\nAnchor.\n",
            b"Local.\nAnchor.\n",
            b"Source.\nAnchor.\n",
            "structure_conflict",
        ),
        (
            b"Repeat.\nAnchor.\nRepeat.\n",
            b"Local.\nAnchor.\nRepeat.\n",
            b"Repeat.\nAnchor.\nSource.\n",
            "structure_ambiguous",
        ),
        (
            b"---\npriority: 1\n---\nText.\n",
            b"---\npriority: 2\n---\nText.\n",
            b"---\npriority: 3\n---\nText.\n",
            "structure_conflict",
        ),
        (
            b'---\nsource_item_id: "one"\npriority: 1\n---\nText.\n',
            b'---\nsource_item_id: "other"\npriority: 1\n---\nText.\n',
            b'---\nsource_item_id: "one"\npriority: 2\n---\nText.\n',
            "structure_identity_conflict",
        ),
    )
    for original, current, incoming, rule in cases:
        change = reconcile(structured_request(original, current, incoming)).changes[0]
        assert change.disposition == "unresolved" and change.result is None
        assert change.provenance.rule == rule
        assert (change.original.data, change.current.data, change.incoming.data) == (
            original,
            current,
            incoming,
        )


def test_clean_textual_merge_duplicate_property_counterexample_is_not_compatible():
    from brz2obsidian.core import reconcile

    original = b"---\na: 1\nb: 1\n---\nText.\n"
    current = b"---\nstatus: local\na: 1\nb: 1\n---\nText.\n"
    incoming = b"---\na: 1\nb: 1\nstatus: source\n---\nText.\n"
    # Independent known clean textual combination: disjoint insertions, duplicate meaning.
    textual_result = b"---\nstatus: local\na: 1\nb: 1\nstatus: source\n---\nText.\n"
    parsed = interpret_structure(ExactContent(data=textual_result), output_format=7)
    assert parsed.status == "unsupported" and parsed.issues == ("duplicate_property",)
    result = reconcile(structured_request(original, current, incoming))
    assert result.changes[0].disposition == "unresolved" and not result.ready


def test_unchanged_incoming_preserves_opaque_bytes_before_structure_interpretation():
    from brz2obsidian.core import reconcile

    original = b"Original.\n"
    current = b"\xff\x00---\r\nduplicate: true\nduplicate: false\n"
    result = reconcile(structured_request(original, current, original))
    change = result.changes[0]
    assert change.disposition == "preserve_vault" and change.result.data == current
    assert change.structure_result is None and result.ready


def test_opaque_field_kind_change_requires_review_instead_of_inventing_scalar_meaning():
    from brz2obsidian.core import reconcile

    original = b"---\ncategories: []\n---\nText.\n"
    incoming = b'---\ncategories: "new scalar"\n---\nText.\n'
    result = reconcile(structured_request(original, original, incoming))
    assert result.changes[0].disposition == "unresolved"
    assert result.changes[0].result is None


def test_already_present_structural_source_changes_need_no_new_review():
    from brz2obsidian.core import reconcile

    original = b"First.\nLast.\n"
    same = b"First.\nChanged last.\n"
    result = reconcile(structured_request(original, same, same))
    change = result.changes[0]
    assert change.disposition == "no_change" and change.result.data == same
    assert not change.requires_decision and result.ready


def test_scalar_types_and_readonly_lists_retain_their_distinct_meanings():
    raw = b'---\ncreated: 2026-10-21\nlabel: "2026-10-21"\nactive: true\nrank: 1\nempty:\ntags:\n  - "one"\n  - "two"\n---\nText.\n'
    doc = interpret_structure(ExactContent(data=raw), output_format=7)
    assert doc.status == "supported"
    assert [(f.key, f.scalar_type, f.value) for f in doc.fields] == [
        ("created", "date", "2026-10-21"),
        ("label", "string", "2026-10-21"),
        ("active", "boolean", True),
        ("rank", "integer", 1),
        ("empty", "null", None),
        ("tags", "opaque", None),
    ]
    for value in (
        b'"unclosed',
        b"01",
        b"1.0",
        b"YES",
        b"2026-02-31",
        b"value # authored comment",
        b"*alias",
    ):
        invalid = interpret_structure(
            ExactContent(data=b"---\nx: " + value + b"\n---\nText.\n"), output_format=7
        )
        assert invalid.status == "unsupported"
    assert interpret_structure(
        ExactContent(data=b"Text.\n"), output_format=6
    ).issues == ("format_unsupported",)


def test_core_scalar_combination_uses_source_neutral_facts_and_validates_candidate():
    from brz2obsidian.contracts import (
        StructureByteEdit,
        StructureComparison,
        StructuredDocument,
        StructureField,
        StructureSpan,
    )
    from brz2obsidian.core import reconcile
    from tests.reconciliation.test_proposals import request

    raw = (
        b"entry:opening|A1|B2|BODY",
        b"entry:opening|A1|B4|LOCAL",
        b"entry:opening|A3|B2|BODY",
    )
    docs = tuple(
        StructuredDocument(
            schema_id="brz2obsidian.structured-document",
            schema_version=1,
            output_format=7,
            content=ExactContent(data=data),
            status="supported",
            issues=(),
            body=StructureSpan(start=20, end=len(data)),
            fields=(
                StructureField(
                    key="foreign-key",
                    kind="identity",
                    identity_component="item",
                    scalar_type="string",
                    value="entry:opening",
                    span=StructureSpan(start=0, end=14),
                    value_span=StructureSpan(start=0, end=13),
                ),
            )
            + tuple(
                StructureField(
                    key=key,
                    kind="scalar",
                    identity_component=None,
                    scalar_type="integer",
                    value=value,
                    span=StructureSpan(start=start, end=end),
                    value_span=StructureSpan(start=start + 1, end=start + 2),
                )
                for key, value, start, end in (
                    ("first", a, 14, 17),
                    ("second", b, 17, 20),
                )
            ),
        )
        for data, a, b in ((raw[0], 1, 2), (raw[1], 1, 4), (raw[2], 3, 2))
    )
    comparison = StructureComparison(
        schema_id="brz2obsidian.structure-comparison",
        schema_version=1,
        original=docs[0],
        current=docs[1],
        incoming=docs[2],
        alignment="supported",
        issues=(),
        local_edits=(
            StructureByteEdit(
                span=StructureSpan(start=0, end=4),
                expected=b"BODY",
                replacement=b"LOCAL",
            ),
        ),
        source_edits=(),
    )
    facts = request(original=raw[0], current=raw[1], incoming=raw[2])
    subject = facts.subjects[0].model_copy(update={"structure": comparison})
    change = reconcile(facts.model_copy(update={"subjects": (subject,)})).changes[0]
    assert change.result.data == b"entry:opening|A3|B4|LOCAL"
    assert [(f.key, f.value) for f in change.structure_result.fields] == [
        ("foreign-key", "entry:opening"),
        ("first", 3),
        ("second", 4),
    ]
    assert len({f.key for f in change.structure_result.fields}) == 3


def test_document_and_edit_facts_cannot_authorize_unbound_bytes():
    from brz2obsidian.contracts import StructureByteEdit, StructureSpan
    from brz2obsidian.core import reconcile

    facts = structured_request(
        b"One.\nMiddle.\nLast.\n",
        b"Local.\nMiddle.\nLast.\n",
        b"One.\nMiddle.\nSource.\n",
    )
    subject = facts.subjects[0]
    comparison = subject.structure
    corruptions = (
        {
            "current": comparison.current.model_copy(
                update={
                    "content": ExactContent(data=b"Different content."),
                    "body": StructureSpan(start=0, end=18),
                }
            )
        },
        {"incoming": comparison.incoming.model_copy(update={"output_format": 6})},
        {"local_edits": ()},
        {
            "source_edits": (
                StructureByteEdit(
                    span=StructureSpan(start=13, end=18),
                    expected=b"Wrong",
                    replacement=b"Source.\n",
                ),
            )
        },
    )
    for update in corruptions:
        changed = subject.model_copy(
            update={"structure": comparison.model_copy(update=update)}
        )
        result = reconcile(facts.model_copy(update={"subjects": (changed,)}))
        change = result.changes[0]
        assert (
            change.disposition == "unresolved"
            and change.provenance.rule == "structure_unbound"
        )
        assert change.result is None and not result.ready


def test_normalized_identity_fields_reject_nontext_identity_even_with_safe_span():
    import pytest
    from pydantic import ValidationError

    from brz2obsidian.contracts import StructureField, StructureSpan

    with pytest.raises(ValidationError, match="identity"):
        StructureField(
            key="imported-id",
            kind="identity",
            identity_component="item",
            value=1,
            scalar_type="integer",
            span=StructureSpan(start=0, end=3),
            value_span=StructureSpan(start=1, end=2),
        )


def test_touching_insert_and_replacement_facts_cannot_bypass_edit_alignment():
    from brz2obsidian.contracts import StructureByteEdit, StructureSpan
    from brz2obsidian.core import reconcile

    facts = structured_request(
        b"One.\nMiddle.\nLast.\n",
        b"Local.\nMiddle.\nLast.\n",
        b"One.\nMiddle.\nSource.\n",
    )
    subject = facts.subjects[0]
    ambiguous = (
        StructureByteEdit(
            span=StructureSpan(start=0, end=0), expected=b"", replacement=b"Local."
        ),
        StructureByteEdit(
            span=StructureSpan(start=0, end=4), expected=b"One.", replacement=b""
        ),
    )
    comparison = subject.structure.model_copy(update={"local_edits": ambiguous})
    changed = subject.model_copy(update={"structure": comparison})
    result = reconcile(facts.model_copy(update={"subjects": (changed,)}))
    assert result.changes[0].provenance.rule == "structure_unbound"
    assert result.changes[0].result is None


def test_structure_assumptions_ignore_locator_aliases_but_bind_changed_facts():
    from hashlib import sha256

    from brz2obsidian.contracts import ImmutableContentReference
    from brz2obsidian.core import reconcile

    facts = structured_request(
        b"One.\nAnchor.\nLast.\n",
        b"Local.\nAnchor.\nLast.\n",
        b"One.\nAnchor.\nSource.\n",
    )
    first = reconcile(facts).changes[0]
    subject = facts.subjects[0]
    doc = subject.structure.current
    reference = ImmutableContentReference(
        content_id="store:alias",
        sha256=sha256(doc.content.data).hexdigest(),
        size=len(doc.content.data),
    )
    aliased = doc.model_copy(
        update={"content": ExactContent(data=doc.content.data, reference=reference)}
    )
    comparison = subject.structure.model_copy(update={"current": aliased})
    repeated = subject.model_copy(update={"structure": comparison})
    same = reconcile(
        facts.model_copy(
            update={
                "subjects": (repeated,),
                "proposal_id": "review:other",
                "generation": 2,
            }
        )
    ).changes[0]
    assert first.change_id == same.change_id and first.assumptions == same.assumptions
    changed = subject.model_copy(
        update={
            "structure": comparison.model_copy(
                update={"alignment": "ambiguous", "issues": ("prose_ambiguous",)}
            )
        }
    )
    invalidated = reconcile(facts.model_copy(update={"subjects": (changed,)})).changes[
        0
    ]
    assert invalidated.change_id != first.change_id
    assert invalidated.provenance.rule == "structure_ambiguous"


def test_structured_candidate_facts_cannot_validate_different_result_bytes():
    import pytest
    from pydantic import ValidationError

    from brz2obsidian.core import reconcile

    facts = structured_request(
        b"First.\nLast.\n", b"Local.\nLast.\n", b"First.\nSource.\n"
    )
    change = reconcile(facts).changes[0]
    with pytest.raises(ValidationError, match="candidate"):
        type(change).model_validate(
            change.model_dump() | {"result": ExactContent(data=b"unbound user bytes")}
        )


def test_markdown_blocks_and_links_do_not_acquire_generated_ownership():
    from brz2obsidian.core import reconcile

    for body in (
        b"    Indented code.\n",
        b"# Generated-looking heading\nText.\n",
        b"[label](other.md)\n",
        b"---\n",
    ):
        result = reconcile(
            structured_request(b"Plain prose.\n", b"Plain prose.\n", body)
        )
        change = result.changes[0]
        assert change.disposition == "unresolved" and change.result is None


def test_reordered_matching_anchors_require_review_of_alignment():
    from brz2obsidian.core import reconcile

    result = reconcile(
        structured_request(
            b"One.\nTwo.\nLast.\n", b"Two.\nOne.\nLast.\n", b"One.\nTwo.\nSource.\n"
        )
    )
    change = result.changes[0]
    assert change.disposition == "unresolved"
    assert change.provenance.rule == "structure_ambiguous"


def test_consistent_but_wrong_parsed_identity_cannot_contradict_selected_inventory_identity():
    from brz2obsidian.core import reconcile

    original = b'---\nsource_item_id: "wrong"\npriority: 1\n---\nText.\n'
    incoming = b'---\nsource_item_id: "wrong"\npriority: 2\n---\nText.\n'
    result = reconcile(structured_request(original, original, incoming))
    change = result.changes[0]
    assert change.identity_review.status == "matched"
    assert change.disposition == "unresolved"
    assert change.provenance.rule == "structure_identity_conflict"


def test_supported_structure_cannot_override_an_explicit_opaque_interpretation():
    from brz2obsidian.core import reconcile

    facts = structured_request(
        b"First.\nLast.\n", b"Local.\nLast.\n", b"First.\nSource.\n"
    )
    subject = facts.subjects[0].model_copy(update={"interpretation": "opaque"})
    result = reconcile(facts.model_copy(update={"subjects": (subject,)}))
    assert result.changes[0].disposition == "unresolved"
    assert result.changes[0].result is None and not result.ready
